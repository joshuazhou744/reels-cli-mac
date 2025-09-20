#!/bin/zsh

SOCKET=/tmp/socket
LINK=$1

mpv --config-dir=./.config/ --input-ipc-server=$SOCKET &

sleep 1

echo "loadfile $LINK append-play" | nc -U $SOCKET