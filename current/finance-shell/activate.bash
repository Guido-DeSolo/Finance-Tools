# Source this file to add Finance Shell to the current Bash session.
_fsh_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$_fsh_dir:$PATH"
unset _fsh_dir
