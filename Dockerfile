# 1. Imagem Base: Comece com uma imagem oficial do Python.
# A imagem 'slim' é menor e mais segura.
FROM python:3.10-slim

# 2. Defina o Diretório de Trabalho: Onde o código viverá dentro do contêiner.
WORKDIR /app

# 3. Copie o arquivo de dependências PRIMEIRO.
# Isso aproveita o cache do Docker. A reinstalação só acontecerá se este arquivo mudar.
COPY requirements.txt requirements.txt

# 4. Instale as dependências.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copie todo o resto do seu código-fonte para o contêiner.
COPY . .

# 6. Exponha a Porta: O Cloud Run se comunica com seu contêiner através de uma porta.
# Usamos a variável $PORT, que o Cloud Run fornece automaticamente.
# O Procfile que criamos anteriormente usa esta mesma variável.
CMD exec uvicorn main:app --host 0.0.0.0 --port $PORT
