import logging
from scrapyd_k8s.joblogs.log_handler_k8s import KubernetesJobLogHandler
from scrapyd_k8s.k8s_resource_watcher import ResourceWatcher

logger = logging.getLogger(__name__)

def joblogs_init(config, resource_watcher):
    """
    Initializes job logs handling by starting the Kubernetes job log handler.

    Parameters
    ----------
    config : Config
        Configuration object containing settings for job logs and storage.

    Returns
    -------
    None
    """
    namespace = config.namespace()
    joblogs_config = config.joblogs()
    if joblogs_config and joblogs_config.get('storage_provider') is not None:
        log_handler = KubernetesJobLogHandler(config)
        resource_watcher.subscribe(log_handler.handle_events)
        logger.info("Job logs handler started.")
    else:
        logger.warning("No storage provider configured; job logs will not be uploaded.")
