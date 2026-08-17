# Security policy

## Supported versions

OmniScript is currently pre-1.0. Security fixes are made on the latest release line.

## Reporting

Please report a suspected vulnerability privately through GitHub's **Security → Report a vulnerability** flow for this repository. Do not include exploit details in a public issue before maintainers have assessed the report.

## Execution model

OmniScript is a general-purpose language, not a security sandbox. Programs can use `read`, `write`, input, and source imports to access resources available to the host process. Run untrusted `.omni` files only inside an appropriately restricted operating-system container or account.
