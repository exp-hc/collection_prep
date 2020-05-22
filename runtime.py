"""
Get ready for 1.0.0
"""
import datetime
import logging
import platform
import os
import sys
import glob

from argparse import ArgumentParser
import ruamel.yaml
from update import load_py_as_ast, find_assigment_in_ast


logging.basicConfig(format="%(levelname)-10s%(message)s", level=logging.INFO)

COLLECTION_MIN_ANSIBLE_VERSION = ">=2.9"
DEPRECATION_CYCLE_IN_YEAR = 2
REMOVAL_FREQUENCY_IN_MONTHS = 3
REMOVAL_DAY_OF_MONTH = "01"


def get_warning_msg(plugin_name):
    today = datetime.date.today()
    deprecation_year = today.year + DEPRECATION_CYCLE_IN_YEAR
    if today.month % REMOVAL_FREQUENCY_IN_MONTHS:
        depcrecation_month = (today.month + REMOVAL_FREQUENCY_IN_MONTHS) - (today.month % REMOVAL_FREQUENCY_IN_MONTHS)
    else:
        depcrecation_month = today.month

    depcrecation_date = f"{deprecation_year}-{depcrecation_month}-{REMOVAL_DAY_OF_MONTH}"
    depcrecation_msg = f"{plugin_name} has been deprecated and will be removed in a release after {depcrecation_date}. See the plugin documentation for more details"
    return depcrecation_msg


def process_runtime_plugin_routing(collection, path):
    plugin_routing = {}
    plugins_path = f"{path}/{collection}/plugins"
    modules_path = f"{plugins_path}/modules"
    action_path = f"{plugins_path}/action"

    collection = collection.replace("/", ".")
    collection_name = collection.split(".")[-1]
    if not collection_name:
        logging.error(f"failed to get collection name from {collection}")

    for fullpath in sorted(glob.glob(f"{modules_path}/*.py")):
        is_depcrecated = False
        filename = fullpath.split("/")[-1]
        if not filename.endswith(".py") or filename.endswith("__init__.py"):
            continue

        module_name = filename.split(".")[0]

        logging.info(
            f"-------------------Processing runtime.yml for module {module_name}"
        )

        ast_obj = load_py_as_ast(fullpath)
        documentation = find_assigment_in_ast(ast_file=ast_obj, name="DOCUMENTATION")
        doc_section = ruamel.yaml.load(
            documentation.value.to_python(), ruamel.yaml.RoundTripLoader
        )

        if "deprecated" in doc_section:
            is_depcrecated = True

        try:
            module_prefix = module_name.split("_")[0]
        except IndexError:
            module_prefix = module_name

        short_name = module_name.split("_", 1)[-1]

        # handle action plugin redirection
        if (
            os.path.exists(os.path.join(action_path, f"{module_prefix}.py"))
            and module_prefix == collection_name
        ):
            fq_action_name = f"{collection}.{module_prefix}"
            if not plugin_routing.get("action"):
                plugin_routing["action"] = {}
            plugin_routing["action"].update({module_name: {"redirect": fq_action_name}})
            plugin_routing["action"].update({short_name: {"redirect": fq_action_name}})

        # handle module short name redirection only in case if module is not deprecated.
        # Add short redirection if module prefix and collection name is same
        # for example arista.eos.eos_acls will support redirection for arista.eos.acls
        # as the prefix of module name (eos) is same as the collection name
        if module_prefix == collection_name and not is_depcrecated:
            fq_module_name = f"{collection}.{module_name}"
            if not plugin_routing.get("modules"):
                plugin_routing["modules"] = {}
            plugin_routing["modules"].update({short_name: {"redirect": fq_module_name}})

        # handle module deprecation notice
        if "deprecated" in doc_section:
            logging.info("Found to be deprecated")
            if not plugin_routing.get("modules"):
                plugin_routing["modules"] = {}
            plugin_routing["modules"].update(
                {
                    module_name: {
                        "deprecation": {
                            "warning_text": get_warning_msg(
                                f"{collection}.{module_name}"
                            )
                        }
                    }
                }
            )

    return plugin_routing


def process(collection, path):
    rt_obj = {}
    rt_obj["requires_ansible"] = COLLECTION_MIN_ANSIBLE_VERSION
    plugin_routing = process_runtime_plugin_routing(collection, path)
    if plugin_routing:
        rt_obj["plugin_routing"] = plugin_routing

    # create meta/runtime.yml file
    meta_path = os.path.join(os.path.join(path, collection), "meta")
    if not os.path.exists(meta_path):
        os.makedirs(meta_path)

    runtime_path = os.path.join(meta_path, "runtime.yml")

    yaml = ruamel.yaml.YAML()
    yaml.explicit_start = True

    with open(runtime_path, "w") as fp:
        yaml.dump(rt_obj, fp)


def main():
    """
    The entry point
    """
    if not platform.python_version().startswith("3.8"):
        sys.exit("Python 3.8+ required")
    parser = ArgumentParser()
    parser.add_argument(
        "-c", "--collection", help="The name of the collection", required=True
    )
    parser.add_argument(
        "-p", "--path", help="The path to the collection", required=True
    )
    args = parser.parse_args()
    process(collection=args.collection, path=args.path)


if __name__ == "__main__":
    main()