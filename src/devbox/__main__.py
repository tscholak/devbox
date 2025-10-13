#!/usr/bin/env python3

import asyncio
import logging
import sys
import warnings

import hydra
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import InterpolationResolutionError

from lambdalabs import ApiError

from devbox.command_base import CommandError
from devbox.commands import command_adapter


log = logging.getLogger("devbox")


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    """Main entry point with Hydra configuration."""
    warnings.simplefilter("default")
    logging.captureWarnings(True)

    try:
        # Parse config to discriminated union type
        config = command_adapter.validate_python(
            OmegaConf.to_container(cfg, resolve=True)
        )

        # Create and run command
        command = config.create_command()
        asyncio.run(command.run())

    except KeyboardInterrupt:
        log.info("Interrupted")
        sys.exit(130)
    except InterpolationResolutionError as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)
    except CommandError as e:
        log.error("Command error: %s", e)
        sys.exit(1)
    except ApiError as e:
        log.error("API error: %s", e)
        sys.exit(1)
    except Exception as e:
        log.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
