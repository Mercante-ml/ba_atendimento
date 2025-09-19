# Usa uma imagem oficial do Python como base
FROM python:3.12-slim

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia o arquivo de requisitos
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do seu código para o contêiner
COPY . .

# Expõe a porta que o Django vai usar
EXPOSE 8000

# Define o comando para iniciar o servidor, sem a subpasta duplicada
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]