name = "aves"

def parse_config(config_file="config.yaml"):
    if config_file.endswith("json"):
        raise ValueError("Please use aves < 3.0.0")
    import yaml
    with open(config_file) as stream:
        data = yaml.safe_load(stream)
    if data["version"] != 2:
        raise ValueError("Don't know how to handle config.yaml with version != 2")
    return data
