```
     _           _
  __| | _____  _| |__   _____  __
 / _` |/ _ \ \/ / '_ \ / _ \ \/ /
| (_| |  __/\  /| |_) | (_) >  <
 \__,_|\___| \/ |_.__/ \___/_/\_\

Lambda Labs GPU instance management for hackers
```

**Status**: v1.0 - Opinionated & Evolving

A CLI tool for managing Lambda Labs GPU instances with persistent storage, cloud-init automation, and intelligent retry logic. Built for the workflow of repeatedly spinning up powerful GPU instances, doing work, and tearing them down—without losing your environment setup.

## Philosophy

- **Persistent everything**: Nix store and home directory survive instance restarts
- **Type-safe end-to-end**: Pydantic models with discriminated unions for compile-time safety
- **Smart retries**: Exponential backoff on capacity issues, fast failure on config errors
- **Visual consistency**: Card-based output format everywhere, no visual surprises
- **Structural pattern matching**: Python 3.10+ pattern matching throughout

## Quick Start

```bash
# Clone and setup
git clone https://github.com/tscholak/devbox.git
cd devbox
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Set your API key
export LAMBDA_API_KEY="your_key_here"

# Launch a GH200 instance
devbox command=up_gh200

# List instances
devbox command=list resource=instances

# SSH into instance
ssh gh200-devbox  # Auto-configured in ~/.ssh/config.d/

# Terminate when done
devbox command=down instance_identifier=gh200-devbox
```

## Features

### Persistent Storage

Instances use Lambda Labs persistent filesystems to maintain state across restarts:

```
/lambda/nfs/devbox/
├── nix/           # 100GB loop device for Nix store
└── ubuntu/        # Home directory bind mount
```

All your packages, configs, and project files survive instance termination.

### Intelligent Launch Retry

Capacity issues? No problem. The CLI automatically retries with exponential backoff:

```
⚠ Insufficient capacity - retrying in 5.0s (attempt 1/21)
⚠ Insufficient capacity - retrying in 7.5s (attempt 2/21)
⚠ Insufficient capacity - retrying in 11.2s (attempt 3/21)
```

But fails fast on actual errors (auth, invalid params, quota exceeded).

### Type-Safe Error Handling

Context-specific error unions using Pydantic discriminated unions:

```python
match error.error:
    case ApiErrorInsufficientCapacity():
        # Retry with backoff
    case ApiErrorQuotaExceeded():
        # Fail immediately
    case _:
        # Handle others
```

Errors are beautifully rendered with structured details:

```
API Error
    Request:  POST /instance-operations/launch
     Status:  400
       Code:  instance-operations/launch/insufficient-capacity
    Message:  Not enough capacity to fulfill launch request.
 Suggestion:  Choose an instance type with more availability, or try again later.
```

### Cloud-Init Automation

Instances automatically configure themselves on first boot:

- Mount persistent filesystem
- Create Nix store loop device (if needed)
- Bind mount home directory
- Install Nix + Home Manager
- Configure as Flakes-enabled dev environment

### Consistent Visual Language

Every command uses the same card-based format:

```
gh200-devbox
        ID:  646044a5f4ee41ff829613a9cbd22438
    Status:  active
        IP:  192.222.58.14
       SSH:  ssh gh200-devbox
    Region:  us-east-3
      Type:  gpu_1x_gh200
```

No jarring table borders, no inconsistent styling, no visual chaos.

## Command Reference

### List Resources

```bash
# List instances
devbox command=list resource=instances

# List available instance types (with capacity)
devbox command=list resource=instance_types

# List images
devbox command=list resource=images

# List filesystems
devbox command=list resource=filesystems

# List SSH keys
devbox command=list resource=ssh_keys

# List firewall rulesets
devbox command=list resource=firewall_rulesets
```

### Launch Instances

```bash
# Launch with all options
devbox command=up \
  region=us-east-3 \
  instance_type=gpu_1x_gh200 \
  ssh_key_name=default \
  filesystem_name=devbox \
  instance_name=my-instance \
  image_id=e57d5fc7-36e7-4f9a-953f-3429c1f7e3b7 \
  wait_after_launch=true

# Or use the GH200 preset
devbox command=up_gh200

# Customize retry behavior
devbox command=up_gh200 \
  max_retries=50 \
  initial_backoff=10.0 \
  max_backoff=180.0 \
  backoff_multiplier=2.0
```

### Manage Instances

```bash
# Wait for instance to be ready
devbox command=wait instance_identifier=gh200-devbox

# Get SSH command
devbox command=ssh instance_identifier=gh200-devbox

# Terminate instance
devbox command=down instance_identifier=gh200-devbox
```

## Configuration

Built on [Hydra](https://hydra.cc) for composable configuration:

```
src/devbox/conf/
├── command/
│   ├── up.yaml          # Base up command config
│   ├── up_gh200.yaml    # GH200-specific preset
│   ├── list.yaml
│   ├── wait.yaml
│   ├── down.yaml
│   └── ssh.yaml
├── api/
│   └── default.yaml     # API client settings
├── wait/
│   └── default.yaml     # Wait/polling settings
└── ssh/
    └── default.yaml     # SSH connection settings
```

Override any setting via CLI:

```bash
devbox command=up_gh200 instance_name=experiment-007 max_retries=100
```

## Why This Exists

Lambda Labs offers incredible GPU compute at reasonable prices, but the workflow of managing ephemeral instances with persistent development environments isn't trivial. This tool encodes my opinionated workflow:

1. **One filesystem per region** with Nix store + home directory
2. **Named instances** with auto-generated SSH configs
3. **Smart retries** because GH200s are in high demand
4. **Type safety** because runtime errors at $2/hr are expensive
5. **Visual consistency** because mental context switching is costly

If this matches your workflow, great. If not, fork it and make it yours.

## Opinions Baked In

- **Nix/NixOS**: The cloud-init assumes you want Nix
- **Loop devices**: 100GB ext4 image for Nix store instead of direct NFS (performance)
- **Home Manager**: Configured but not auto-installed (you do that)
- **SSH config.d/**: Uses per-instance config files instead of one giant config
- **Card-based UI**: Small 2-column tables, no borders, cyan headers everywhere
- **Exponential backoff**: Because capacity is more available at odd hours
- **Python 3.13**: Uses latest type hints and pattern matching

## License

MIT - Do whatever you want with it

## Contributing

This is a personal tool made public. PRs welcome but I reserve the right to be opinionated about what gets merged. Fork freely if our opinions diverge.

---

*Built with Python 3.13, Pydantic 2.x, Hydra 1.3, Rich, and strong opinions.*

*Includes Lambda Cloud API spec v1.8.3*
