# Hosting Sentinel on AWS — Step by Step

What this gets you: one command creates a real AWS server, a second command puts Sentinel on it and starts it. Everything lives in the `terraform/` folder.

Read this top to bottom once before running anything — especially the **cost** and **teardown** sections near the end, since this creates real, billed AWS resources.

---

## What actually gets created

- One EC2 virtual machine (default size: `t3.large`, 8GB RAM — big enough for the backend's embedding model)
- A fixed public IP address (Elastic IP) so it doesn't change if the server restarts
- A firewall rule (security group) that only allows: SSH (so you can log in) and web traffic (80/443, so the dashboard is reachable)
- Nothing else — no database service, no load balancer, no Kubernetes. Just one VM, matching how Sentinel is designed to run.

`terraform apply` builds the *empty* server (installs Python, Node.js, nginx — the ingredients). `deploy.sh` then copies your actual Sentinel code onto it and starts it — two separate steps on purpose, so infrastructure and application deploys don't get tangled together.

---

## Prerequisites (do these once)

1. **An AWS account** with billing set up, and a way to authenticate — the simplest is the AWS CLI:
   - Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
   - Run `aws configure` and paste in your Access Key ID / Secret Access Key (from the AWS Console → IAM → your user → Security credentials).
2. **Terraform** installed locally: https://developer.hashicorp.com/terraform/install
   - Confirm with `terraform -version`.
3. **An SSH key pair** on your machine. If you don't have one yet:
   ```bash
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
   ```
   (Terraform's default config expects `~/.ssh/id_rsa.pub` — change `ssh_public_key_path` in your tfvars if yours lives elsewhere.)
4. **A working local Sentinel setup** — specifically, a `.env` file at the repo root and a `frontend/.env.local` file, the same ones you already use for `python -m services.main` / `npm run dev` locally. `deploy.sh` copies these up as-is; if they don't exist yet, get local dev working first.
5. **Git Bash** (Windows) or any POSIX shell (Mac/Linux) — `deploy.sh` uses `rsync` and `ssh`, both of which Git Bash already has.

---

## Step by step

### 1. Configure your variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and check:
- `ssh_public_key_path` — points at your `.pub` file
- `allowed_ssh_cidr` — defaults to "anywhere" so it works immediately; **tighten this to your own IP once you've confirmed access** (find your IP with `curl -s https://checkip.amazonaws.com`, then set it to `"<that-ip>/32"`)
- `instance_type` — `t3.large` is the default; drop to `t3.medium` if you're just kicking the tires and want it cheaper

### 2. Create the server

```bash
terraform init      # downloads the AWS plugin, one-time per machine
terraform plan       # shows exactly what it's about to create — read it
terraform apply      # type "yes" when prompted
```

This takes a couple of minutes. When it finishes, note the output:
```
dashboard_url = "http://<some-ip>"
ssh_command   = "ssh ubuntu@<some-ip>"
```

The server then spends another 2-4 minutes on its own finishing setup in the background (installing Python/Node/nginx) — `deploy.sh` in the next step automatically waits for that to finish, so you don't need to time it yourself.

### 3. Ship the code and start it

```bash
./deploy.sh
```

This copies your local Sentinel code to the server, installs its dependencies, builds the frontend, and starts both services. Takes a few minutes (mostly `npm install`/`npm run build`). When it's done, it prints the dashboard URL.

### 4. Open it

Visit `http://<the-ip-from-step-2>` in your browser. Log in the same way you do locally.

### 5. Point your test runs at it

Anywhere you'd normally run `playwright test` (locally or in CI) with the `@sentinel/playwright` reporter configured, set:
```bash
SENTINEL_BASE_URL=http://<the-ip-from-step-2>
SENTINEL_API_KEY=<whatever you set LIVE_INGEST_API_KEY to in your .env>
```
and runs will show up live on this server instead of your laptop.

---

## Making changes later

Edited the code? Just rerun:
```bash
./deploy.sh
```
It re-syncs and restarts the services. It won't touch your AWS infrastructure (VM, IP, firewall) — that only changes if you edit the `.tf` files and run `terraform apply` again.

---

## Optional: a real domain + HTTPS

By default you get plain HTTP on the raw IP. To add a domain with a proper certificate:

1. Point your domain's DNS `A` record at the `dashboard_url` IP from step 2.
2. SSH in (`ssh ubuntu@<ip>`) and run:
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```
   Certbot edits the nginx config and sets up auto-renewal for you.

---

## Cost

Roughly (US East, on-demand pricing, will vary — check the [AWS pricing page](https://aws.amazon.com/ec2/pricing/on-demand/) for current numbers):

| Item | Approx. monthly cost |
|---|---|
| `t3.large` instance, running 24/7 | ~$60 |
| `t3.medium` instead | ~$30 |
| 50GB gp3 EBS volume | ~$4 |
| Elastic IP (while attached to a running instance) | free; a few dollars/month if the instance is stopped but the IP is kept |

If you're only testing, `terraform destroy` (below) when you're done stops the billing entirely — there's no cheaper "pause" state for an EC2 instance's compute cost.

---

## Tearing it down

```bash
cd terraform
terraform destroy
```

Type "yes" when prompted. This deletes the VM, its disk, and the IP — everything Terraform created. **Anything not backed up elsewhere is gone with it** — the LanceDB data on that server's disk is not automatically backed up anywhere by this setup (see the backup guidance in `LIVE_EXECUTION_VM_DEPLOYMENT.md`).

---

## If something's not working

- **`deploy.sh` hangs on "waiting for the VM to finish its cloud-init bootstrap"**: SSH in manually (`ssh ubuntu@<ip>`) and check `sudo tail -f /var/log/sentinel-bootstrap.log` for what's stuck.
- **Dashboard loads but shows errors**: check the backend directly — `ssh ubuntu@<ip> 'sudo journalctl -u sentinel-backend -n 50'`.
- **Frontend won't load at all**: `ssh ubuntu@<ip> 'sudo journalctl -u sentinel-frontend -n 50'`.
- **Live runs don't show up live (only after refresh)**: almost always an nginx buffering issue — confirm `sudo nginx -T | grep proxy_buffering` shows `off` for the `/live/` location (the bootstrap script sets this already, but check if you've since edited the nginx config by hand).
