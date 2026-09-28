#!/bin/bash

CONTENEDOR="pg-abogados"

# Verifica si el contenedor ya existe
if [ "$(docker ps -aq -f name=$CONTENEDOR)" ]; then
    echo "El contenedor ya existe, iniciándolo..."
    docker start $CONTENEDOR
else
    echo "Creando contenedor nuevo..."
    docker run --name $CONTENEDOR \
        -e POSTGRES_USER=usuario \
        -e POSTGRES_PASSWORD=password \
        -e POSTGRES_DB=basedatos \
        -p 15432:5432 \
        -v pg-abogados-data:/var/lib/postgresql/data \
        -d pgvector/pgvector:pg16
fi

echo "Postgres corriendo en localhost:15432"