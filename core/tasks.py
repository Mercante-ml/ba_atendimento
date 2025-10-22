# core/tasks.py

import pandas as pd
import numpy as np
import json
import os
from celery import shared_task
import google.generativeai as genai  # ALTERADO: Importa a biblioteca correta
from google.generativeai.types import HarmCategory, HarmBlockThreshold # ADICIONADO: Para configurações de segurança
from django.conf import settings
from .models import ProcessedFile
from dotenv import load_dotenv  # ADICIONADO: Para carregar o .env

# ADICIONADO: Carrega as variáveis de ambiente (do .env)
load_dotenv()

# ADICIONADO: Configura a API Key do Gemini a partir do .env
# Certifique-se que seu .env tenha a linha: GOOGLE_API_KEY="sua_chave_aqui"
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("A variável de ambiente GOOGLE_API_KEY não foi definida no .env")
genai.configure(api_key=GEMINI_API_KEY)

# REMOVIDO: Bloco de configuração do Vertex AI
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/gcloud_credentials.json"
#GOOGLE_CLOUD_PROJECT = "dv-ia-ingestion"
#GOOGLE_CLOUD_LOCATION = "us-east1"
#GOOGLE_GENAI_USE_VERTEXAI = True
#client = genai.Client(...)

# Configuração do prompt do Gemini
si_text = """Você é um assistente especializado em extração de dados de reclamações sobre telecomunicações.
Sua tarefa é extrair as informações do texto da reclamação de forma precisa e estrita, conforme solicitado abaixo.
Para cada campo, procure a informação exata no texto. NÃO faça suposições.
Se um campo não estiver explicitamente presente, retorne o valor como None.

Informações desejadas:
1) O número de origem (Número de A).
    Para retornar a origem, considere o que vem a seguir de expressões como ("ORIGEM", "NUMERO A"). Se tiver mais de um número de origem, retorne uma lista todos os numeros encontrados.
2) O número de destino (Número de B).
    Para retornar a destino, considere o que vem a seguir de expressões como ("DESTINO", "NUMERO B"). Se tiver mais de um número de destino, retorne uma lista todos os numeros encontrados.
3) Chave/identificador (DDD + Telefone ou apenas Telefone)
    Para retornar a chave/identificador, considere o que vem a seguir de expressões como ("RELACLAMADO", "IDENTIFICADOR", "TESTADO", "NÚMERO CHAVE", "VINCULADO").  Se tiver mais de um número de chave, retorne uma lista todos os numeros encontrados.
4) Localidade, cidade, estado ou DDD da reclamação.
    Para retornar o local, considere CEP, Nomes de Cidade ou Estado ou mesmo o DDD do telefone reclamado.
5) A data e a hora exatas em que os testes foram realizados (ex: 27/08/2025 16:52).
    Para retornar a data e hora dos testes, considere a hora da reclamação, ou da indicação de algum teste. Se tiver mais de um teste, retorne uma lista com as Datas e Horas.
6) Reclamação.
    Para retornar a problema, considere a parte do texto que indica o problema a ser resolvido.
7) O nome completo do cliente que fez a reclamação. Não confundir com o nome do técnico.
    Para retornar o nome, considere nomes que não estejam indicados como o técnico de solução que não é o cliente.

Retorne no formato json com os campos 'origem', 'destino', 'identificador', 'local', 'data_hora', 'problema' e 'nome', respectivamente.
"""

generate_content_config = genai.GenerationConfig(
    temperature=1.0,
    top_p=0.95,
    max_output_tokens=65535,
)

# 'types.SafetySetting' vira um formato diferente
safety_settings = [
    {
        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
]

# ADICIONADO: Instancia o modelo
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash", 
    generation_config=generate_content_config,
    system_instruction=si_text,
    safety_settings=safety_settings
)


#
# <<< --- A FUNÇÃO QUE FALTAVA ESTÁ AQUI --- >>>
#
# Função para chamar o Gemini (adaptada para a API Padrão)
def generate_from_gemini(texto):
    # A API padrão aceita o texto diretamente
    contents = [texto]
    
    # ADICIONADO: Define um timeout de 60 segundos
    request_options = {"timeout": 60}
    
    # A chamada é feita diretamente no 'model'
    response_chunks = model.generate_content(
        contents,
        stream=True,
        request_options=request_options
    )
    
    full_response = "".join([chunk.text for chunk in response_chunks])
    clean_response = full_response.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_response)


# A Tarefa do Celery
@shared_task(bind=True)
def processar_planilha_com_ia(self, file_id):
    processed_file = None
    try:
        processed_file = ProcessedFile.objects.get(id=file_id)
        caminho_entrada = os.path.join(settings.MEDIA_ROOT, processed_file.file_name)
        nome_saida = f"processado_{processed_file.file_name}"
        caminho_saida = os.path.join(settings.MEDIA_ROOT, nome_saida)

        processed_file.status = 'Em Processamento'
        processed_file.save()

        # Lê a segunda aba do arquivo Excel
        df = pd.read_excel(caminho_entrada, sheet_name=1)
        
        coluna_descricao = 'DESCRIÇÃO'
        if coluna_descricao not in df.columns:
            raise KeyError(f"A coluna '{coluna_descricao}' não foi encontrada no arquivo Excel.")
        
        df_descricao = pd.DataFrame()
        df_descricao['descricao'] = df[coluna_descricao].astype(str)
        
        resultados = []
        
        # ADICIONADO: Pega o total de linhas para o log
        total_linhas = len(df_descricao['descricao'])
        print(f"[CELERY] Inciando processamento. Total de linhas: {total_linhas}")

        for i, texto in enumerate(df_descricao['descricao']):
            
            # ADICIONADO: Log de progresso
            print(f"[CELERY] Processando linha {i+1} de {total_linhas}...")
            
            try:
                resultado = generate_from_gemini(texto)
                resultados.append(resultado)
            except Exception as e:
                # ADICIONADO: Log de erro
                print(f"[CELERY] ERRO na linha {i+1}: {str(e)}")
                resultados.append({"erro": str(e)}) # Salva o erro (timeout, etc)
        
        print("[CELERY] Processamento do loop concluído. Salvando arquivo...")
        df_resultados = pd.DataFrame(resultados)
        df_final = pd.concat([df, df_resultados], axis=1)
        
        df_final.to_excel(caminho_saida, index=False)
        
        processed_file.status = 'Concluído'
        processed_file.download_url = nome_saida
        processed_file.save()
        
        print("[CELERY] Tarefa concluída com sucesso.")
        return {"status": "sucesso", "caminho_saida": caminho_saida}
        
    except ProcessedFile.DoesNotExist:
        print(f"Erro: O arquivo com ID {file_id} não foi encontrado no banco de dados.")
        return {"status": "erro", "mensagem": f"Arquivo com ID {file_id} não encontrado."}
    
    except KeyError as e:
        if processed_file:
            processed_file.status = 'Falha'
            processed_file.save()
        return {"status": "erro", "mensagem": f"Erro de coluna no Excel: {str(e)}"}
        
    except Exception as e:
        if processed_file:
            processed_file.status = 'Falha'
            processed_file.save()
        print(f"[CELERY] Erro inesperado: {str(e)}") 
        return {"status": "erro", "mensagem": f"Erro inesperado: {str(e)}"}

