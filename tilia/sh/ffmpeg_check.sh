#!/bin/bash
if command -v ffmpeg &> /dev/null
then
    exit 0
else
    exit 1
fi
