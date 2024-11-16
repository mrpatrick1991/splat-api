FROM --platform=linux/amd64 python:3.11-slim

ENV HOME="/root"
ENV TERM=xterm

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    build-essential \
    libbz2-dev

WORKDIR /app/splat
RUN chmod +x build
RUN chmod +x configure
RUN chmod +x install


# Pass inputs to the configure script
RUN printf "8\n0\n" | ./configure
RUN ./install splat

RUN bash -c "splat"
