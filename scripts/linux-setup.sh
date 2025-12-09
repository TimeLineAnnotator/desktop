#!/usr/bin/env bash

echo "Setup Linux build environment"
trap 'echo Setup failed; exit 1' ERR

df -h .

##########################################################################
# GET DEPENDENCIES
##########################################################################

apt_packages=(
  coreutils
  curl
  gawk
  git
  lcov
  libasound2-dev
  libcups2-dev
  libfontconfig1-dev
  libfreetype6-dev
  libgcrypt20-dev
  libgl1-mesa-dev
  libglib2.0-dev
  libjack-dev
  libnss3-dev
  libportmidi-dev
  libpulse-dev
  librsvg2-dev
  libsndfile1-dev
  libssl-dev
  libtool
  make
  p7zip-full
  sed
  unzip
  wget
  )

apt_packages_runtime=(
  # Alphabetical order please!
  libdbus-1-3
  libegl1-mesa-dev
  libgles2-mesa-dev
  libodbc2
  libpq-dev
  libssl-dev
  libxcomposite-dev
  libxcursor-dev
  libxi-dev
  libxkbcommon-x11-0
  libxrandr2
  libxtst-dev
  libdrm-dev
  libxcb-cursor-dev
  libxcb-icccm4
  libxcb-image0
  libxcb-keysyms1
  libxcb-randr0
  libxcb-render-util0
  libxcb-xinerama0
  libxcb-xkb-dev
  libxkbcommon-dev
  libopengl-dev
  libvulkan-dev
  )

apt_packages_ffmpeg=(
  ffmpeg
  libavcodec-dev
  libavformat-dev
  libswscale-dev
  )

apt_packages_pw_deps=(
  libdbus-1-dev
  libudev-dev
  )

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  "${apt_packages[@]}" \
  "${apt_packages_runtime[@]}" \
  "${apt_packages_ffmpeg[@]}" \
  "${apt_packages_pw_deps[@]}"

##########################################################################
# PIPEWIRE
##########################################################################

sudo apt-get install pipewire-media-session- wireplumber

systemctl --user --now enable wireplumber.service
