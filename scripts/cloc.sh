cloc $(find . -maxdepth 1 -type d \
    ! -name '.' \
    ! -name '.*' \
    ! -name 'node*')
