from __future__ import annotations

import unittest
from unittest.mock import patch

from web_api.errors import ApiError
from web_api.services import auth


class AuthJwksTests(unittest.TestCase):
    def setUp(self) -> None:
        auth._JWKS_CACHE_BY_KID.clear()
        auth._JWKS_CACHE_EXPIRES_AT = 0.0

    def tearDown(self) -> None:
        auth._JWKS_CACHE_BY_KID.clear()
        auth._JWKS_CACHE_EXPIRES_AT = 0.0

    def test_get_jwk_by_kid_reuses_stale_cache_when_refresh_fails(self) -> None:
        auth._JWKS_CACHE_BY_KID["kid-1"] = {"kid": "kid-1", "kty": "RSA"}
        auth._JWKS_CACHE_EXPIRES_AT = 1.0

        with patch("web_api.services.auth.time.time", return_value=10.0):
            with patch(
                "web_api.services.auth._fetch_jwks",
                side_effect=ApiError("UNAUTHORIZED", "读取登录服务密钥失败：timed out", 401),
            ):
                jwk = auth._get_jwk_by_kid("http://auth.local/api/auth/jwks", "kid-1")

        self.assertEqual(jwk, {"kid": "kid-1", "kty": "RSA"})
        self.assertGreater(auth._JWKS_CACHE_EXPIRES_AT, 10.0)

    def test_get_jwk_by_kid_raises_when_no_cache_and_refresh_fails(self) -> None:
        with patch("web_api.services.auth.time.time", return_value=10.0):
            with patch(
                "web_api.services.auth._fetch_jwks",
                side_effect=ApiError("UNAUTHORIZED", "读取登录服务密钥失败：timed out", 401),
            ):
                with self.assertRaises(ApiError):
                    auth._get_jwk_by_kid("http://auth.local/api/auth/jwks", "kid-1")


if __name__ == "__main__":
    unittest.main()
