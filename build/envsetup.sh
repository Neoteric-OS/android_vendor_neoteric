function __print_neoteric_functions_help() {
cat <<EOF
Additional Neoteric functions:
- clodiff:         Utility to diff CLO history to Neoteric.
- clomerge:        Utility to merge CLO tags.
- roomservice:     Utility to sync device dependencies.
- sort-blobs-list: Sort proprietary-files.txt sections with LC_ALL=C.
EOF
}

red='\033[0;31m'
cyan='\033[0;36m'
nocol='\033[0m'

function clodiff()
{
    target_branch=$1
    set_stuff_for_environment
    T=$(gettop)
    python3 $T/vendor/neoteric/build/tools/diff-clo.py $target_branch
}

function clomerge()
{
    target_branch=$1
    push=$2
    set_stuff_for_environment
    T=$(gettop)
    python3 $T/vendor/neoteric/build/tools/merge-clo.py $target_branch $push
}

function roomservice() {
    if [ -z "$TARGET_PRODUCT" ]; then
        echo -e "$red*******************************************************************************************************"
        echo    " SEEMS LIKE LUNCH COMMAND HAS NOT BEEN EXECUTED YET, EXECUTE LUNCH TO PROPERLY SETUP BUILD ENVIRONMENT "
        echo -e "*******************************************************************************************************$nocol"
        return
    fi
    T=$(gettop)
    TARGET_MANUFACTURER=$(get_build_var PRODUCT_MANUFACTURER 2>/dev/null | tr '[:upper:]' '[:lower:]')
    if [ -f "device/$TARGET_MANUFACTURER/$TARGET_PRODUCT/neoteric.dependencies" ]; then
        python3 $T/vendor/neoteric/build/tools/roomservice.py device/$TARGET_MANUFACTURER/$TARGET_PRODUCT
    else
        echo "Roomservice configuration not found in device tree, aborting roomservice."
        return
    fi
}

function sort-blobs-list() {
    T=$(gettop)
    $T/tools/extract-utils/sort-blobs-list.py $@
}

function genkeys() {
    T=$(gettop)
    certs_dir="${ANDROID_BUILD_TOP}/certs"
    if [ "$(ls "$certs_dir" 2>/dev/null | wc -l)" -ne 0 ]; then
        read -p "Signing keys seem to be already there. Do you want to continue? (Y/N): " SIGN_RESP
        case $SIGN_RESP in
            [yY] )
                find "$certs_dir" -mindepth 1 \
                  -not -name '.git' -not -name '.gitignore' -not -path "$certs_dir/.git/*" \
                  -exec rm -rf {} +
                ;;
            *)
                return
                ;;
        esac
    fi
    echo -e "$red**********************************************"
    echo    "   SIGNING KEYS NOT FOUND!, GENERATING THEM"
    echo -e "**********************************************$nocol"

    # Make directory
    mkdir -p "$certs_dir"

    # Subject details
    subject="/O=Neoteric/OU=Neoteric/CN=Neoteric"

    # Make keys
    local keys=( releasekey devkey platform shared media networkstack nfc testkey sdk_sandbox bluetooth )
    for key in "${keys[@]}"; do
        ./development/tools/make_key "$certs_dir/$key" "$subject"
    done
}

CLANG_VERSION=$(build/soong/scripts/get_clang_version.py)
export LLVM_AOSP_PREBUILTS_VERSION="${CLANG_VERSION}"

RUST_VERSION=$(grep 'RustDefaultVersion =' build/soong/rust/config/global.go | awk '{print $3}' | awk -F '"' '{print $2}')
export RUST_AOSP_PREBUILTS_VERSION="${RUST_VERSION}"

export SKIP_ABI_CHECKS="true"
export RELAX_USES_LIBRARY_CHECK=true

if [ -n "$TARGET_PRODUCT" ]; then
    roomservice
fi
