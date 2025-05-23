version: 0.2

env:
  variables:
    TMPDIR: /tmp
phases:
  build:
    on-failure: ABORT
    commands:   
      - echo "this build spec is expected to be over-ridden"
