#!/bin/bash
# Auto update Quake Live workshop items for all individual instances on the host

STEAMCMD="/home/ql/Steam/steamcmd.sh"
BASE_DIR="/home/ql"
QLDS_BASE_DIR="$BASE_DIR/qlds-base"
QLDS_BASE_CONTENT_DIR="$QLDS_BASE_DIR/steamapps/workshop/content/282440"

#######################################################################
# 1. Update qlds-base: derive IDs from already-downloaded content dirs
#######################################################################
if [ -d "$QLDS_BASE_CONTENT_DIR" ]; then
    BASE_WORKSHOPS=()
    for dir in "$QLDS_BASE_CONTENT_DIR"/*/; do
        id=$(basename "$dir")
        if [[ "$id" =~ ^[0-9]+$ ]]; then
            BASE_WORKSHOPS+=("$id")
        fi
    done

    if [ ${#BASE_WORKSHOPS[@]} -gt 0 ]; then
        chown -R ql:ql "$QLDS_BASE_DIR/steamapps"

        echo "--------------------------------------------------------"
        echo "Processing workshop updates for qlds-base"

        for ITEM_ID in "${BASE_WORKSHOPS[@]}"; do
            echo "Downloading workshop item $ITEM_ID ..."
            sudo -u ql "$STEAMCMD" \
                +force_install_dir "$QLDS_BASE_DIR" \
                +login anonymous \
                +workshop_download_item 282440 "$ITEM_ID" validate \
                +quit
        done

        echo "Done updating items into $QLDS_BASE_CONTENT_DIR"
    fi
fi

#######################################################################
# 2. Update instances: use workshop.txt as source of truth
#######################################################################

# Ensure we cleanly handle the glob if no matches are found
shopt -s nullglob
INSTANCES=("$BASE_DIR"/qlds-*)
shopt -u nullglob

VALID_INSTANCES=()
for dir in "${INSTANCES[@]}"; do
    # Only target actual directories and explicitly ignore qlds-base
    if [[ "$dir" != "$QLDS_BASE_DIR" && -d "$dir" ]]; then
        VALID_INSTANCES+=("$dir")
    fi
done

for INSTANCE_DIR in "${VALID_INSTANCES[@]}"; do
    WORKSHOPFILE="$INSTANCE_DIR/baseq3/workshop.txt"

    # Skip to the next instance if it doesn't have a workshop file defined
    if [ ! -f "$WORKSHOPFILE" ]; then
        continue
    fi

    # Read workshop IDs into an array, ignoring comments and empty lines
    # (using `|| true` to prevent potential script crashes if run with `set -e`)
    mapfile -t WORKSHOPS < <(grep -E -v '^\s*(#|$)' "$WORKSHOPFILE" || true)

    # Skip to the next instance if its workshop file was completely empty
    if [ ${#WORKSHOPS[@]} -eq 0 ]; then
        continue
    fi

    # Ensure the steamapps folder exists and properly owned
    mkdir -p "$INSTANCE_DIR/steamapps"
    chown -R ql:ql "$INSTANCE_DIR/steamapps"

    echo "--------------------------------------------------------"
    echo "Processing workshop updates for instance: $INSTANCE_DIR"

    # Download each workshop item locally into this specific instance
    for ITEM in "${WORKSHOPS[@]}"; do
        # Extract just the numeric ID in case there are inline trailing comments (e.g. `123123 # Map name`)
        ITEM_ID=$(echo "$ITEM" | awk '{print $1}')

        if [[ -n "$ITEM_ID" && "$ITEM_ID" =~ ^[0-9]+$ ]]; then
            echo "Downloading workshop item $ITEM_ID ..."
            sudo -u ql "$STEAMCMD" \
                +force_install_dir "$INSTANCE_DIR" \
                +login anonymous \
                +workshop_download_item 282440 "$ITEM_ID" validate \
                +quit
        fi
    done

    echo "Done updating items into $INSTANCE_DIR/steamapps/workshop/content/282440"
done

echo "--------------------------------------------------------"
echo "Workshop update process completed for all instances."
