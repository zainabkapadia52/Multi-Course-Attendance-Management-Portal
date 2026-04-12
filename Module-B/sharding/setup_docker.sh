#!/bin/bash
# =============================================================
#   CS 432 - Assignment 4: Sharding
#   Docker Container Setup Script
#   Run this FIRST before any Python scripts
# =============================================================
# Shard 0 - port 3307
docker run --name shard_0 \
  -e MYSQL_ROOT_PASSWORD=shardpass \
  -e MYSQL_DATABASE=shard_db_0 \
  -p 3307:3306 \
  -d mysql:8

# Shard 1 - port 3308
docker run --name shard_1 \
  -e MYSQL_ROOT_PASSWORD=shardpass \
  -e MYSQL_DATABASE=shard_db_1 \
  -p 3308:3306 \
  -d mysql:8

# Shard 2 - port 3309
docker run --name shard_2 \
  -e MYSQL_ROOT_PASSWORD=shardpass \
  -e MYSQL_DATABASE=shard_db_2 \
  -p 3309:3306 \
  -d mysql:8

sleep 5  # Wait for MySQL containers to initialize

# Wait ~20 seconds for MySQL to initialise, then verify all 3 are running
docker ps