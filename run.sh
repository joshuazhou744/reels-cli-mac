#!/bin/bash

SOCKET=/tmp/socket

mpv --config-dir=./.config/ --input-ipc-server=$SOCKET &

sleep 1

for LINK in "$@"; do
    if [[ -n "$LINK" ]]; then
        echo "loadfile \"$LINK\" append-play" | nc -U $SOCKET
        sleep 0.1
    fi
done