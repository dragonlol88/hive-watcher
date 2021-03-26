import pytest


@pytest.fixture
def watcher_address():
    return ('0.0.0.0', 7777)


@pytest.fixture
def client_address():
    return ('0.0.0.0', 6666)


@pytest.fixture
def root_dir():
    return "../data/project"


@pytest.fixture
def ignore_pattern():
    return '.*swp|4913|.*~|.*swx:'


@pytest.fixture
def proj_depth():
    return 1


@pytest.fixture
def host():
    return '0.0.0.0'


@pytest.fixture
def port():
    return 7777


@pytest.fixture
def event_num():
    return 2


@pytest.fixture
def stored_directory():
    return './watcher_directory'


@pytest.fixture
def origin_text():
    return {
                "test_project_stopword_210330.txt": ["about", "all", "any", "because", "been", "being"],
                "test_project_synonym_210330.txt": ["A.C.,A.C,AC", "Air Changes per hour,AC/h", "A.E.,A.E,AE", "A.F.,A.F,AF"]
            }
