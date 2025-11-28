"""
Pytest configuration for property tests.

Adds --chaos flag for running tests under adversarial conditions.
"""

import pytest


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--chaos",
        action="store_true",
        default=False,
        help="Run tests under chaos conditions (network partitions, delays, etc.)"
    )


def pytest_configure(config):
    """Configure pytest based on command line options"""
    if config.getoption("--chaos"):
        print("\n🌪️  CHAOS MODE ENABLED - Testing under adversarial conditions\n")
        config.addinivalue_line(
            "markers", "chaos: marks tests as chaos resilience tests"
        )


@pytest.fixture(scope="session")
def chaos_mode(request):
    """Fixture that provides chaos mode status"""
    return request.config.getoption("--chaos")
