name = "aves"

def parse_config(config_file="config.json"):
    import json
    with open(config_file) as data_file:
        data = json.load(data_file)
    if data["version"] != 1:
        raise ValueError("Don't know how to handle config.json with version != 1")
    return data

