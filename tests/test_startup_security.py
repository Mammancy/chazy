import os
import unittest
from unittest.mock import patch

from app.config.settings import get_settings, validate_production_jwt_secret


class StartupSecurityTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def test_production_rejects_default_jwt_secret(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "change-this-development-jwt-secret"}):
            get_settings.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET_KEY is weak"):
                validate_production_jwt_secret()

    def test_production_rejects_short_jwt_secret(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "short-secret"}):
            get_settings.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "shorter than 32 characters"):
                validate_production_jwt_secret()

    def test_production_accepts_strong_jwt_secret(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "a-unique-production-secret-with-48-characters!!"}):
            get_settings.cache_clear()
            validate_production_jwt_secret()

    def test_development_allows_default_jwt_secret(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "JWT_SECRET_KEY": "change-this-development-jwt-secret"}):
            get_settings.cache_clear()
            validate_production_jwt_secret()


if __name__ == "__main__":
    unittest.main()
