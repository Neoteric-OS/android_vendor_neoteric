#!/usr/bin/env python3
#
#
# Copyright (C) 2023 Paranoid Android
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Merge script for Neoteric

 The source directory; this is automatically two folder up because the script
 is located in vendor/neoteric/build/tools. Other ROMs will need to change this. The logic is
 as follows:

 1. Get the absolute path of the script with os.path.realpath in case there is a symlink
    This script may be symlinked by a manifest so we need to account for that
 2. Get the folder containing the script with dirname
 3. Move into the folder that is three folders above that one and print it

"""

import argparse
import os
import shutil
import subprocess
import xml.etree.ElementTree as Et

import git
from git.exc import GitCommandError

BASE_URL = "https://git.codelinaro.org/clo/la/"
WORKING_DIR = "{0}/../../../..".format(os.path.dirname(os.path.realpath(__file__)))
MANIFEST_NAME = "neoteric.xml"
REPOS_TO_MERGE = {}
REPOS_RESULTS = {}

# useful helpers
def nice_error():
    """ Errors out in a non-ugly way. """
    print("Invalid repo, are you sure this repo is on the tag you're merging?")


def get_manual_repos(args, is_system):
    """ Get all manually (optional) specified repos from arguments """
    ret_lst = {}
    default_repos = list_default_repos(is_system)
    if args.repos_to_merge:
        for repo in args.repos_to_merge:
            if repo not in default_repos:
                nice_error()
                return None, None
            ret_lst[repo] = default_repos[repo]
    return ret_lst, default_repos


def list_default_repos(is_system):
    """ Gathers all repos from split system.xml and vendor.xml """
    default_repos = {}
    if is_system:
        with open(
            "{0}/.repo/manifests/system.xml".format(WORKING_DIR)
        ) as system_manifest:
            system_root = Et.parse(system_manifest).getroot()
            for child in system_root:
                path = child.get("path")
                if path:
                    default_repos[path] = child.get("name")
    else:
        with open(
            "{0}/.repo/manifests/vendor.xml".format(WORKING_DIR)
        ) as vendor_manifest:
            vendor_root = Et.parse(vendor_manifest).getroot()
            for child in vendor_root:
                path = child.get("path")
                if path:
                    default_repos[path] = child.get("name")
    return default_repos


def read_custom_manifest(default_repos):
    """ Finds all repos that need to be merged """
    print("Finding repos to merge...")
    with open("{0}/.repo/manifests/{1}".format(WORKING_DIR, MANIFEST_NAME)) as manifest:
        root = Et.parse(manifest).getroot()
        removed_repos = []
        project_repos = []
        reversed_default = {value: key for key, value in default_repos.items()}
        for repo in root:
            if repo.tag == "remove-project":
                removed_repos.append(repo.get("name"))
            else:
                if repo.get("remote") == "neoteric":
                    project_repos.append(repo.get("path"))

        for repo in removed_repos:
            if repo in reversed_default:
                if reversed_default[repo] in project_repos:
                    REPOS_TO_MERGE[reversed_default[repo]] = repo


def force_sync(repo_lst):
    """ Force syncs all the repos that need to be merged """
    print("Syncing repos")
    for repo in repo_lst:
        if os.path.isdir("{}{}".format(WORKING_DIR, repo)):
            shutil.rmtree("{}{}".format(WORKING_DIR, repo))

    cpu_count = str(os.cpu_count())
    args = [
        "repo",
        "sync",
        "-c",
        "--force-sync",
        "-f",
        "--no-tags",
        "-j",
        cpu_count,
        "-q",
    ] + list(repo_lst.values())
    subprocess.run(
        args,
        check=False,
    )

def merge(repo_lst, is_system, branch):
    """ Merges the necessary repos and lists if a repo succeeds or fails """
    failures = []
    successes = []

    for repo in repo_lst:
        if repo == "device/qcom/common":
            print(f"Skipping merge for {repo} as per exception rule.")
            continue  # Skip this repository

        print("Merging " + repo)
        os.chdir("{0}/{1}".format(WORKING_DIR, repo))

        try:
            # Parse the XML file to get the revision
            manifest_file = "{0}/.repo/manifests/system.xml".format(WORKING_DIR) if is_system else "{0}/.repo/manifests/vendor.xml".format(WORKING_DIR)
            with open(manifest_file) as manifest:
                root = Et.parse(manifest).getroot()
                revision = None

                # Find the revision for the current repo
                for child in root.findall("project"):
                    if child.get("path") == repo:
                        revision = child.get("revision")
                        break

            if not revision:
                print(f"Failed to find revision for {repo} in {manifest_file}")
                failures.append(repo)
                continue

            # Fetch the branch associated with the revision
            remote_url = "{}{}".format(BASE_URL, repo_lst[repo])
            git.cmd.Git().fetch(remote_url, revision)

            # Merge the fetched revision into the current branch with a custom message
            branch_name = branch.replace("refs/tags/", "")
            merge_msg = f"Merge tag '{branch_name}' of {remote_url} into HEAD\n{branch_name}"
            git.cmd.Git().merge(revision, m=merge_msg)

            successes.append(repo)
        except GitCommandError as git_error:
            print(git_error)
            failures.append(repo)

    REPOS_RESULTS.update({"Successes": successes, "Failures": failures})


def merge_manifest(is_system, branch):
    if is_system:
        manifest_name = "system"
    else:
        manifest_name = "vendor"

    manifest_path = "{0}/.repo/manifests/{1}.xml".format(WORKING_DIR, manifest_name)

    # Construct the raw URL for the manifest file
    raw_url = f"https://git.codelinaro.org/clo/la/la/{manifest_name}/manifest/-/raw/{branch}/{branch}.xml"
    print(f"Downloading manifest from: {raw_url}")

    # Download the manifest using curl. --fail keeps CLO error pages (404 for a
    # bad tag, 429 when rate limited) from being written out as the manifest,
    # and --retry rides out the rate limiting.
    subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--retry",
            "5",
            "--retry-delay",
            "10",
            "-o",
            manifest_path,
            raw_url
        ],
	check=True
    )

    # Ensure shallow cloning for each project in the manifest only for system
    with open(manifest_path) as manifestxml:
        tree = Et.parse(manifestxml)
        root = tree.getroot()

        # Remove CLO remotes
        for elem in root.findall("remote") + root.findall("default"):
            root.remove(elem)

	# Remove refs
        for refs in root.findall("refs"):
            root.remove(refs)
	    
        # Shallow clone
        if is_system:
            for project in root.findall("project"):
                project.set("clone-depth", "1")  # Set clone-depth for shallow clone if applicable

        # Write the updated manifest back to file
        tree.write(manifest_path)

    print(f"{manifest_name}.xml downloaded successfully.{' Shallow clone settings applied.' if is_system else ''}")


def print_results(branch):
    """ Prints all repos that will need to be manually fixed """
    if REPOS_RESULTS["Failures"]:
        print("\nThese repos failed to merge, fix manually: ")
        for failure in REPOS_RESULTS["Failures"]:
            print(failure)
    if REPOS_RESULTS["Successes"]:
        print("\nRepos that merged successfully: ")
        for success in REPOS_RESULTS["Successes"]:
            print(success)
    print()
    if not REPOS_RESULTS["Failures"] and REPOS_RESULTS["Successes"]:
        print(
            "{0} merged successfully!".format(
                branch.split("/")[2]
            )
        )
    elif not REPOS_RESULTS["Failures"] and not REPOS_RESULTS["Successes"]:
        print("Unable to retrieve any results")


def push_successful_repos(successful_repos, is_system, branch):
    revision = None
    with open("{0}/.repo/manifests/default.xml".format(WORKING_DIR)) as default_manifest:
        default_tree = Et.parse(default_manifest)
        default_root = default_tree.getroot()
        neoteric_remote = default_root.find("remote[@name='neoteric']")
        if neoteric_remote is not None:
            revision = neoteric_remote.get("revision")
            print(f"Revision for neoteric remote: {revision}")

    # Push manifest changes
    if is_system:
        manifest_name = "system"
    else:
        manifest_name = "vendor"
    manifest_path = f"{WORKING_DIR}/.repo/manifests"
    os.chdir(manifest_path)
    try:
        git.cmd.Git().add(f"{manifest_name}.xml")  # Stage all changes
        git.cmd.Git().commit(m=f"{manifest_name}: Update to {branch}", s=True)  # Commit with the provided message
        git.cmd.Git().push("origin", f"HEAD:{revision}", "--force")
        print(f"Pushing {manifest_path} changes to Neoteric.")
    except GitCommandError as git_error:
        print(f"Failed to commit changes in {manifest_path}: {git_error}")

    # Push repository changes
    for repo in successful_repos:
        repo_path = f"{WORKING_DIR}/{repo}"
        print(f"Pushing {repo} to Neoteric...")
        os.chdir(repo_path)
        try:
            git.cmd.Git().push("neoteric", f"HEAD:{revision}", "--force")
            print(f"{repo} pushed successfully.")
        except GitCommandError as git_error:
            print(f"Failed to push {repo}: {git_error}")


def main():
    """Gathers and merges all repos from CLO and
    reports all repos that need to be fixed manually"""

    parser = argparse.ArgumentParser(description="Merge a CLO revision.")
    parser.add_argument(
        "branch_to_merge",
        metavar="branch",
        type=str,
        help="a tag to merge from git.codelinaro.org",
    )
    parser.add_argument(
        "--repos",
        dest="repos_to_merge",
        nargs="*",
        type=str,
        help="path of repos to merge",
    )
    parser.add_argument(
        "--push",
        dest="push",
        action="store_true",
        help="Push each repository to github",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Dry run the merge script (for testing purposes)",
    )
    args = parser.parse_args()

    branch = "refs/tags/{}".format(args.branch_to_merge)

    is_system = "LA.QSSI" in branch
    repo_lst, default_repos = get_manual_repos(args, is_system)
    if repo_lst is None and default_repos is None:
        return
    if len(repo_lst) == 0:
        read_custom_manifest(default_repos)
        if args.dry_run:
            print(list(REPOS_TO_MERGE.keys()))
            quit()
        if REPOS_TO_MERGE:
            merge_manifest(is_system, args.branch_to_merge)
            force_sync(REPOS_TO_MERGE)
            merge(REPOS_TO_MERGE, is_system, branch)
            os.chdir(WORKING_DIR)
            print_results(branch)
            if args.push:
                if REPOS_RESULTS["Successes"]:  # Push only successful repos
                    push_successful_repos(REPOS_RESULTS["Successes"], is_system, args.branch_to_merge)
        else:
            print("No repos to sync")
    else:
        force_sync(repo_lst)
        merge(repo_lst, branch)
        os.chdir(WORKING_DIR)
        print_results(branch)
        if args.push:
            if REPOS_RESULTS["Successes"]:  # Push only successful repos
                push_successful_repos(REPOS_RESULTS["Successes"], is_system, args.branch_to_merge)


if __name__ == "__main__":
    # execute only if run as a script
    main()
