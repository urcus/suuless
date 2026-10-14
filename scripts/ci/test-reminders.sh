#!/usr/bin/env bash
set -euo pipefail
classes="$(mktemp -d)"
trap 'rm -rf -- "$classes"' EXIT
javac -d "$classes" android/app/src/main/java/eu/cormerais/stopclop/ReminderPolicy.java tests/java/ReminderPolicyTest.java
java -cp "$classes" eu.cormerais.stopclop.ReminderPolicyTest
