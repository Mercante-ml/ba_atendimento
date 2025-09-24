# core/tasks.py

import pandas as pd
import numpy as np
import json
import os
from celery import shared_task
from google import genai
from google.genai import types
from django.conf import settings
from .models import ProcessedFile

# Adicione a variável de ambiente para as credenciais
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/gcloud_credentials.json"

# Configurações do Google Cloud (substitua pelos seus valores)
GOOGLE_CLOUD_PROJECT = "dv-ia-ingestion"
GOOGLE_CLOUD_LOCATION = "us-east1"
GOOGLE_GENAI_USE_VERTEXAI = True

client = genai.Client(
    vertexai=GOOGLE_GENAI_USE_VERTEXAI,
    project=GOOGLE_CLOUD_PROJECT,
    location=GOOGLE_CLOUD_LOCATION,
)

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

generate_content_config = types.GenerateContentConfig(
    temperature=1.0,
    top_p=0.95,
    max_output_tokens=65535,
    safety_settings=[
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    ],
    system_instruction=[types.Part.from_text(text=si_text)],
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    seed=42,
)

# Função para chamar o Gemini (adaptada para a nova arquitetura)
def generate_from_gemini(texto):
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=texto)]),
    ]
    response_chunks = client.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=contents,
        config=generate_content_config,
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
        
        # --- Lógica de busca pela coluna ---
        coluna_descricao = 'DESCRIÇÃO' # Nome da coluna que foi confirmado
        
        if coluna_descricao not in df.columns:
            raise KeyError(f"A coluna '{coluna_descricao}' não foi encontrada no arquivo Excel.")
        
        # Cria o DataFrame de descrição, usando a coluna confirmada
        df_descricao = pd.DataFrame()
        df_descricao['descricao'] = df[coluna_descricao].astype(str)
        
        # --- Fim da Lógica de busca ---
        
        # ... (o resto do seu código de processamento com a IA) ...
        resultados = []
        for i, texto in enumerate(df_descricao['descricao']):
            # ... (sua lógica de chamada à API do Gemini) ...
            try:
                resultado = generate_from_gemini(texto)
                resultados.append(resultado)
            except Exception as e:
                resultados.append({"erro": str(e)})
        
        df_resultados = pd.DataFrame(resultados)
        df_final = pd.concat([df, df_resultados], axis=1)
        
        df_final.to_excel(caminho_saida, index=False)
        
        processed_file.status = 'Concluído'
        processed_file.download_url = nome_saida
        processed_file.save()
        
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
        return {"status": "erro", "mensagem": f"Erro inesperado: {str(e)}"}

        df_resultados = pd.DataFrame(resultados)
        df_final = pd.concat([df, df_resultados], axis=1)
        
        # Salva o resultado
        df_final.to_excel(caminho_saida, index=False)
        
        # Atualiza o status e a URL para download
        processed_file.status = 'Concluído'
        processed_file.download_url = nome_saida
        processed_file.save()

        return {"status": "sucesso", "caminho_saida": caminho_saida}

    except Exception as e:
        processed_file.status = 'Falha'
        processed_file.save()
        return {"status": "erro", "mensagem": str(e)}