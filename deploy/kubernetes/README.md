# Kubernetes examples

Generic manifests for one SuuLess instance with persistent SQLite storage. Follow the [deployment guide](../../docs/deployment/kubernetes.md) before applying them.

Copy this directory into ignored `local/kubernetes-example/`, set a real image and suitable storage, then render with `kubectl kustomize local/kubernetes-example`. The example image is deliberately a placeholder; no public release is assumed to exist.

The base includes Namespace, PVC, Deployment and ClusterIP Service. `ingress.yaml` is optional and requires an installed Ingress controller, DNS and a TLS secret. These files contain no private registry addresses, credentials or installation-specific certificates.
