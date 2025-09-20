#!/bin/bash

SOCKET=/tmp/socket
LINK=$1

echo "loadfile $LINK append-play" | nc -U $SOCKET