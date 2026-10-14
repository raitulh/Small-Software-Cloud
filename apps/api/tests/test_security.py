from app.security import create_access_token, decode_access_token, hash_password, verify_password

def test_password_hash_round_trip():
    password = "correct horse battery staple 2026!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong password", hashed)

def test_access_token_round_trip():
    token, expires = create_access_token("8cb806b6-bd9b-4c0a-91a9-1cbb57100ecb")
    assert expires > 0
    assert decode_access_token(token) == "8cb806b6-bd9b-4c0a-91a9-1cbb57100ecb"

def test_invalid_token_rejected():
    assert decode_access_token("not.a.token") is None
