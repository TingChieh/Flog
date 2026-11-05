from tests.conftest import login


def test_public_article_surfaces_have_no_management_controls(client, users):
    login(client, 'admin')

    for path in ('/', f'/post/{users["post"]}'):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert f'/post/{users["post"]}/edit' not in html
        assert f'/post/delete/{users["post"]}' not in html
