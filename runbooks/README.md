# Runbooks

One file per procedure someone might need to follow under pressure.

A runbook is written for the person who did not build the thing, at 3am, who has
not read the code. Write the commands out. Do not write "restart the service" —
write the command that restarts the service.

Every runbook has: symptom, impact, immediate action, diagnosis, resolution,
prevention. If you cannot fill in "prevention", the incident is not finished.

| Runbook | For |
|---|---|
| [cost-freeze-triggered.md](cost-freeze-triggered.md) | Spend crossed the ceiling and the SCP attached |
| [onboard-to-aws.md](onboard-to-aws.md) | Giving someone their AWS sign-in, and the three ceilings behind an AccessDenied |
| [sealed-secrets-key-backup-and-restore.md](sealed-secrets-key-backup-and-restore.md) | Backing up the sealed-secrets controller key, and restoring it when `SealedSecret`s stop decrypting |
