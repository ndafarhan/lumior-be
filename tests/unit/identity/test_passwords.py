from argon2 import PasswordHasher

from lumior.modules.identity.passwords import hash_password, verify_password


async def test_hash_is_argon2id_and_not_the_password() -> None:
    password_hash = await hash_password("correct horse")

    assert password_hash.startswith("$argon2id$")
    assert "correct horse" not in password_hash


async def test_correct_password_verifies() -> None:
    password_hash = await hash_password("correct horse")

    result = await verify_password(password_hash, "correct horse")

    assert result.valid
    assert not result.needs_rehash


async def test_wrong_password_does_not_verify() -> None:
    password_hash = await hash_password("correct horse")

    assert not (await verify_password(password_hash, "wrong horse")).valid


async def test_unknown_user_never_verifies() -> None:
    assert not (await verify_password(None, "lumior-dummy-password")).valid


async def test_malformed_hash_does_not_verify() -> None:
    assert not (await verify_password("not-a-hash", "anything")).valid


async def test_outdated_parameters_need_rehash() -> None:
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw-12345")

    result = await verify_password(weak_hash, "pw-12345")

    assert result.valid
    assert result.needs_rehash
