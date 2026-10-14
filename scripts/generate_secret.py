"""Generate a high-entropy secret for local configuration."""
import secrets

if __name__ == "__main__":
    print(secrets.token_urlsafe(48))
