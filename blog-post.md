---
title: "Stop Buying Home Supercomputers"
date: 2025-01-15
tags: [gpu, infrastructure, nix, cloud]
---

NVIDIA just released the Spark—a $4,000 "supercomputer for the home" with dual RTX 5090s. The marketing copy writes itself: "Desktop AI development without cloud vendor lock-in!" "Own your compute!" The AI influencer crowd is already posting unboxing videos.

It's superslow for real work. And here's why the entire premise is backwards.

## The False Binary

The discourse around GPU compute has calcified into two camps:

1. **Buy hardware**: Own a $4,000+ box gathering dust between experiments
2. **Rent everything**: Pay AWS/Azure markup on H100 time you don't need

Both are wrong. The real question isn't ownership vs rental—it's *granularity of commitment*.

What you actually want: burst access to serious compute (8x H100, GH200) when you need it, zero fixed costs when you don't, and your development environment persisting across sessions. The Spark gives you none of this. AWS gives you two of three at 3x the price.

Lambda Labs gives you all three at $2/hr.

## What's Actually Hard

Renting compute isn't hard. What's hard is the workflow:

```
$ launch instance
... wait 10 minutes for instance
... ssh in
... install nix
... clone repos
... configure environment
... actually do work
... terminate instance
... lose all setup
```

Next day: repeat. The friction makes you *avoid* using the hardware you're paying for.

The problem isn't the cloud—it's the imperative ceremony. Every launch is archaeology: "What packages did I have installed last time?" "Where did I put that config?" "Why isn't this building anymore?"

## Declarative Ephemeral Infrastructure

The solution is obvious once you see it: persistent storage + declarative environment + intelligent retry.

```bash
devbox command=up_gh200
# Launches GH200 instance with:
# - Persistent NFS filesystem mounted at /lambda/nfs/devbox
# - Nix store on 100GB loop device (survives termination)
# - Home directory bind-mounted from NFS
# - SSH config auto-generated
# - Exponential backoff retry on capacity issues
```

Instance terminates when you're done. Your entire environment persists. Next launch picks up exactly where you left off—same packages, same configs, same /nix/store contents.

This is the correct abstraction layer. Not "buy a box" vs "rent a box"—but "disposable compute + durable state".

## Implementation Notes

The interesting bits aren't the cloud API wrapper (that's just Pydantic + aiohttp). The interesting bits are:

### 1. Persistent Nix Store

Nix store can't live directly on NFS (too slow). Solution: 100GB ext4 loop device on NFS, mounted at /nix on boot:

```yaml
# cloud-init fragment
runcmd:
  - |
    if [ ! -f {{ filesystem_mount }}/nix.img ]; then
      dd if=/dev/zero of={{ filesystem_mount }}/nix.img bs=1M count=102400
      mkfs.ext4 {{ filesystem_mount }}/nix.img
    fi
  - mkdir -p /nix
  - mount -o loop {{ filesystem_mount }}/nix.img /nix
```

This gives you proper filesystem performance for Nix operations while keeping state on persistent storage.

### 2. Intelligent Launch Retry

GH200 capacity is scarce. The naive approach fails immediately on `InsufficientCapacity`. The correct approach:

```python
match e.error:
    case ApiErrorInsufficientCapacity():
        if attempt >= self.config.max_retries:
            raise
        attempt += 1
        await asyncio.sleep(backoff)
        backoff = min(
            backoff * self.config.backoff_multiplier,
            self.config.max_backoff,
        )
    case _:
        # Auth errors, quota exceeded, etc. → fail immediately
        raise
```

Exponential backoff with ceiling. Retry capacity errors, fail fast on config errors. Capacity usually appears within 5-20 minutes.

### 3. Type-Safe Error Handling

The Lambda API returns different error schemas depending on endpoint context. Most clients use `dict[str, Any]` and hope. Wrong approach.

Correct approach: discriminated unions per endpoint:

```python
InstanceLaunchError = Annotated[
    ApiErrorUnauthorized
    | ApiErrorAccountInactive
    | ApiErrorLaunchResourceNotFound
    | ApiErrorInvalidParameters
    | ApiErrorInsufficientCapacity
    | ApiErrorQuotaExceeded
    | ...,
    Field(discriminator="code"),
]

instance_launch_error_adapter: TypeAdapter[InstanceLaunchError] = TypeAdapter(
    InstanceLaunchError
)
```

Parser catches schema mismatches at API boundary. Pattern matching ensures exhaustive error handling. No silent failures, no `KeyError` in production.

## What This Enables

With this setup:

- Rent GH200 ($2.49/hr) only when doing actual training
- Environment setup is *zero seconds* (it's already there)
- Can terminate/relaunch freely—state persists
- Total monthly cost: hours_used × $2.49
- Spark equivalent: $4,000 ÷ $2.49 = 1,606 hours = you'd need to use it 200+ hours/month to break even

The Spark makes economic sense if you're running 24/7 jobs. But if you're running 24/7 jobs, you need way more than dual 5090s—you need a cluster.

For everyone else: rent the burst, own the state, declare the environment.

## On Ownership

There's a seductive narrative about "owning your infrastructure." But ownership has granularity:

- Own your **data**: yes, always
- Own your **environment definition**: yes (Nix flake)
- Own your **persistent state**: yes (your NFS filesystem)
- Own your **compute hardware**: only if utilization > 60%

The Spark conflates these. You *can* own data/environment/state without owning silicon.

"But vendor lock-in!" Lambda's API is straightforward HTTP. The entire client is 467 lines. Migrating to another provider is a weekend. That's not lock-in—that's just being pragmatic about where to apply effort.

## Conclusion

The NVIDIA Spark exists because "AI supercomputer for your home office" sounds better than "expensive space heater that's slower than renting."

The correct answer to "should I buy a Spark?" is: *do you have a 60%+ duty cycle workload?*

If yes: buy a Spark (or better: build a proper rig).

If no: use this instead.

The code is MIT licensed, ~1200 lines, passes mypy strict. It does one thing: makes ephemeral GPU compute feel permanent.

[github.com/tscholak/devbox](https://github.com/tscholak/devbox)

---

*Built with Python 3.13, Pydantic 2.x, Hydra, and strong opinions about what "ownership" actually means.*
