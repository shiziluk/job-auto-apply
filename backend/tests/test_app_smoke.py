import os
import tempfile
import unittest
from pathlib import Path

_test_data_dir = Path(tempfile.mkdtemp(prefix="job-auto-apply-test-"))
os.environ["APP_DEBUG"] = "false"
os.environ["DATA_DIR"] = str(_test_data_dir)
os.environ["DB_URL"] = f"sqlite:///{(_test_data_dir / 'test.db').as_posix()}"

from fastapi.testclient import TestClient

from main import app


class AppSmokeTest(unittest.TestCase):
    def test_app_starts_and_serves_health(self):
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")
            self.assertEqual(response.json()["database"], "ok")

    def test_api_routes_are_registered(self):
        with TestClient(app) as client:
            response = client.get("/openapi.json")
            self.assertEqual(response.status_code, 200)
            self.assertIn("/api/auth/login", response.json()["paths"])


if __name__ == "__main__":
    unittest.main()
