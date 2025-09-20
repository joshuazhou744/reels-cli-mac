#!/bin/bash

SOCKET=/tmp/socket

echo '{ "command": ["playlist-remove", 0] }' | nc -U $SOCKET