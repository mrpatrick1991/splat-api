FROM python:3.11-slim

ENV HOME="/root"
ENV TERM=xterm

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    build-essential \
    libbz2-dev \
    imagemagick

WORKDIR /app/splat
RUN chmod +x build && chmod +x configure && chmod +x install

# Modify build script and configure SPLAT!
# Replace fixed CPU / architectures with native
# Use the maximum resolution allowed and do not build splat-hd (options 8 and 0 in configure) 
RUN sed -i.bak 's/-march=\$cpu/-march=native/g' build && \
    printf "8\n0\n" | ./configure && \ 
    ./install splat

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]