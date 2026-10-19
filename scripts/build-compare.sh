#!/usr/bin/env bash
# Build all before/after samples and print a size comparison table.
# Usage: ./scripts/build-compare.sh
set -euo pipefail
cd "$(dirname "$0")/.."

build() {
  local name=$1 dir=$2 file=$3
  echo "building $name ..."
  docker build -q -f "samples/$dir/$file" -t "audit-$name" "samples/$dir" > /dev/null
}

build python-before app-python Dockerfile.before
build python-after  app-python Dockerfile.after
build node-before   app-node   Dockerfile.before
build node-after    app-node   Dockerfile.after
build go-before     app-go     Dockerfile.before
build go-after      app-go     Dockerfile.after

echo
printf '%-14s %-16s\n' "image" "size"
for n in python-before python-after node-before node-after go-before go-after; do
  size=$(docker images --format '{{.Size}}' "audit-$n")
  printf '%-14s %-16s\n' "audit-$n" "$size"
done
