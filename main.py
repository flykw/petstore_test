import json
import requests
from io import BytesIO
import pytest

BASE_URL = "https://petstore.swagger.io/v2"

def load_openapi_spec():
    """
    Загружает спецификацию OpenAPI и возвращает её в виде словаря.
    """
    response = requests.get(f"{BASE_URL}/swagger.json")
    if response.status_code == 200:
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            pytest.skip(f"Ошибка парсинга JSON: {e}")
    else:
        pytest.skip(f"Ошибка при загрузке спецификации: {response.status_code}")

def list_methods(spec):
    """
    Формирует список методов из спецификации:
    Каждый элемент списка – кортеж: (HTTP-метод, path, описание метода).
    """
    methods_list = []
    for path, methods in spec.get('paths', {}).items():
        for method, info in methods.items():
            methods_list.append((method.lower(), path, info))
    return methods_list

def generate_data(param):
    """
    Генерирует данные для параметра, основываясь на его типе.
    Для:
      - integer -> 1;
      - string -> "example";
      - boolean -> True;
      - file -> BytesIO с тестовыми данными.
    """
    # Иногда тип параметра может быть указан в ключе 'schema'
    param_type = param.get('type')
    if not param_type:
        schema = param.get('schema', {})
        param_type = schema.get('type', 'string')

    if param_type == 'integer':
        return 1
    elif param_type == 'string':
        return "example"
    elif param_type == 'boolean':
        return True
    elif param_type == 'file':
        return BytesIO(b"Sample file content")
    return "example"

def prepare_parameters(parameters, path):
    """
    Подготавливает параметры для запроса.
      - Обрабатывает query-параметры.
      - Подставляет данные в URL для path-параметров.
      - Формирует formData-параметры: для типа file – files, для остальных – data.
      - Если указан параметр body – генерирует JSON-данные.
    Возвращает кортеж: (url, query_params, form_data, files, body_data).
    """
    query_params = {}
    form_data = {}
    files = {}
    body_data = None

    for param in parameters:
        location = param.get('in')
        if location == 'query':
            query_params[param['name']] = generate_data(param)
        elif location == 'path':
            value = generate_data(param)
            path = path.replace(f"{{{param['name']}}}", str(value))
        elif location == 'formData':
            # Если параметр типа file, добавляем его в files
            if param.get('type', 'string') == 'file':
                files[param['name']] = ('sample.txt', generate_data(param), 'application/octet-stream')
            else:
                form_data[param['name']] = generate_data(param)
        elif location == 'body':
            body_data = {}
            schema = param.get('schema', {})
            properties = schema.get('properties', {})
            for prop_name, prop_details in properties.items():
                body_data[prop_name] = generate_data(prop_details)
    url = BASE_URL + path
    return url, query_params, form_data, files, body_data

def call_api(method, path, parameters):
    """
    Формирует и выполняет запрос к API.
    В зависимости от наличия query-параметров, formData и тела запроса,
    данные отправляются через параметры url, data, files или json.
    Возвращает объект Response.
    """
    url, query_params, form_data, files, body_data = prepare_parameters(parameters, path)

    headers = {}
    if body_data is not None and not form_data and not files:
        headers['Content-Type'] = 'application/json'

    # Вывод для отладки можно раскомментировать при необходимости
    # print("\n--- Структура запроса ---")
    # print(f"Метод: {method.upper()}")
    # print(f"URL: {url}")
    # if headers:
    #     print(f"Заголовки: {headers}")
    # if query_params:
    #     print(f"Параметры query: {query_params}")
    # if form_data:
    #     print(f"Параметры formData: {form_data}")
    # if files:
    #     print(f"Файлы: {', '.join(files.keys())}")
    # if body_data:
    #     print(f"Тело запроса (body): {body_data}")
    # print("--------------------------")

    try:
        if method == 'get':
            response = requests.get(url, params=query_params, headers=headers)
        elif method == 'post':
            # Если имеется тело запроса и нет formData/файлов, отправляем JSON
            if body_data is not None and not form_data and not files:
                response = requests.post(url, params=query_params, json=body_data, headers=headers)
            else:
                response = requests.post(url, params=query_params, data=form_data, files=files, headers=headers)
        elif method == 'put':
            if body_data is not None and not form_data and not files:
                response = requests.put(url, params=query_params, json=body_data, headers=headers)
            else:
                response = requests.put(url, params=query_params, data=form_data, files=files, headers=headers)
        elif method == 'delete':
            response = requests.delete(url, params=query_params, headers=headers)
        else:
            pytest.skip(f"Неподдерживаемый метод: {method}")
    except Exception as e:
        pytest.fail(f"Ошибка при выполнении запроса: {e}")

    return response

def test_api_method(method, path, method_info):
    """
    Тест для одного метода API.
    Выполняется запрос и проверяется, что ответ имеет корректный HTTP-статус.
    """
    parameters = method_info.get('parameters', [])
    # Вывод информации для отладки о тестируемом методе
    print("\n===================================")
    print(f"Проверяется метод: {method.upper()} {path}")
    if parameters:
        for param in parameters:
            param_type = param.get('type')
            if not param_type:
                param_type = param.get('schema', {}).get('type', 'N/A')
            print(f" - Параметр: {param['name']}, Расположение: {param.get('in', 'N/A')}, Тип: {param_type}")
    else:
        print("Параметры отсутствуют.")

    response = call_api(method, path, parameters)
    print(f"Результат запроса: {response.status_code}")
    try:
        print("Ответ (JSON):", response.json())
    except Exception:
        print("Ответ (TEXT):", response.text)

    assert response.status_code in [200, 201, 204], f"Метод {method.upper()} {path} вернул код {response.status_code}"
    print("Тест пройден успешно.")
    print("===================================\n")

def pytest_generate_tests(metafunc):
    """
    Динамическая параметризация теста test_api_method.
    При запуске тестов загружается спецификация и для каждого метода создается тест.
    """
    if {"method", "path", "method_info"}.issubset(metafunc.fixturenames):
        spec = load_openapi_spec()
        if not spec:
            pytest.skip("Спецификация не загружена")
        methods_list = list_methods(spec)
        metafunc.parametrize("method,path,method_info", methods_list)

