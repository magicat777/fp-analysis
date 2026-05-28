---
name: fpreports.click WHOIS verification fragility
description: Domain registration was placed on clientHold 2026-05-28 because the registrant email was a placeholder (admin@example.com); ICANN WHOIS verification went undeliverable and Gandi suspended DNS publication
metadata:
  type: project
---

**Incident (2026-05-28):** `fpreports.click` returned NXDOMAIN at every public DNS resolver despite AWS infrastructure (S3, CloudFront, Route53) being fully healthy. Root cause was registrar-level `clientHold` status.

**Why:**
- Domain was registered 2026-04-01 via Route53 Domains (backed by Gandi registrar) with placeholder contacts (`admin@example.com`, `123 Main St`, `+1.5551234567`)
- ICANN mandates registrar-verified contact reachability — Gandi sent a verification email to `admin@example.com` which is a dead inbox
- After the verification grace period expired (~30+ days, status: `EXPIRED`), Gandi set EPP `clientHold` per ICANN policy
- `clientHold` is an EPP status code that tells the TLD registry to STOP publishing the domain's NS records — DNS goes dark at the TLD even though Route53 nameservers continue answering queries directly

**How to apply:**

When `fpreports.click` (or any AWS-hosted domain) suddenly stops resolving:

1. **Don't troubleshoot AWS first** — if CloudFront, Route53 hosted zone, and the S3 bucket all look healthy via AWS CLI, the failure is at the registrar/registry layer
2. **Query WHOIS directly** to check for `clientHold` / `serverHold` / `pendingDelete`:
   ```powershell
   $tcp = New-Object System.Net.Sockets.TcpClient; $tcp.Connect("whois.nic.click", 43)
   # ...write "fpreports.click\n" then read response
   ```
3. **Check Route53 Domains reachability status:**
   ```bash
   aws route53domains get-contact-reachability-status --domain-name fpreports.click --profile fp-deploy --region us-east-1
   ```
   If status is `EXPIRED`, verification has lapsed
4. **Fix path:**
   - Update all four contact emails (Registrant, Admin, Tech, Billing) to a real monitored inbox via `aws route53domains update-domain-contact`
   - **The Registrant change triggers ICANN's CoR (Change of Registrant) dual-confirmation** — emails go to both old AND new addresses. With a bouncing old address, the new-side confirmation alone is often enough for Route53 + Gandi to complete the change
   - Click the verification link in the new email (Gmail). Reachability flips from `EXPIRED` to `DONE`
   - Gandi lifts `clientHold` within minutes; .click TLD republishes the delegation within ~5-15 minutes; DNS resolves globally

**Standing risk RESOLVED (2026-05-28):** Address and phone updated from placeholders (123 Main St / +1.5551234567) to real values (707 Highland Ave Apt 2, San Mateo CA 94401 / +1.6507938140). All four contacts (Registrant, Admin, Tech, Billing) now have valid, deliverable data on every field. No IRTP confirmation was required because Registrant email/name/org didn't change.

**Diagnostic commands (saved for fast retrieval):**

```bash
# Are we authenticated?
aws sts get-caller-identity --profile fp-deploy

# Is CloudFront healthy?
aws cloudfront get-distribution --id E3TOOZU85OXSCW --profile fp-deploy --query "Distribution.{Status:Status,Enabled:DistributionConfig.Enabled}"

# Does the CloudFront edge serve the file directly? (proves S3+CF+ACM are fine)
curl -I https://d3su2cp3wkc330.cloudfront.net/fp_report_<location>.html

# Is the domain itself OK at the registrar?
aws route53domains get-domain-detail --domain-name fpreports.click --profile fp-deploy --region us-east-1
aws route53domains get-contact-reachability-status --domain-name fpreports.click --profile fp-deploy --region us-east-1

# Final WHOIS truth (status flags live here):
# TCP/43 to whois.nic.click with "fpreports.click\n"
```

**Cross-references:**
- [[reference_apis]] — has the AWS resource IDs (S3 bucket, CloudFront distribution, Route53 zone)
- AWS infrastructure was NOT the failure point — verified working throughout the incident
