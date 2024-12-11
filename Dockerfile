FROM python:3.11-slim

ENV HOME="/root"
ENV TERM=xterm

# Install system dependencies first (before Python dependencies)
RUN apt-get update && apt-get install -y \
    build-essential \
    libbz2-dev \
    gdal-bin \
    libgdal-dev \
    && apt-get clean

# Set the working directory
WORKDIR /app

# Copy requirements first to leverage Docker caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Change to SPLAT directory and set permissions
WORKDIR /app/splat
RUN chmod +x build && chmod +x configure && chmod +x install

# Modify build script and configure SPLAT
RUN sed -i.bak 's/-march=\$cpu/-march=native/g' build && \
    printf "8\n4\n" | ./configure && \
    ./install splat
# RUN cp ./splat /app/splat

# SPLAT utils including srtm2sdf
WORKDIR /app/splat/utils
RUN chmod +x build
RUN ./build all && cp srtm2sdf /app && cp srtm2sdf-hd /app
RUN cp -a ./ /app/splat

WORKDIR /app
RUN chmod +x /app/splat/splat
RUN chmod +x /app/splat/srtm2sdf
RUN chmod +x /app/splat/citydecoder
RUN chmod +x /app/splat/bearing
RUN chmod +x /app/splat/fontdata
RUN chmod +x /app/splat/usgs2sdf
RUN ls -alh
# Expose the application port
EXPOSE 8080