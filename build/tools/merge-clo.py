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
import time
import xml.etree.ElementTree as Et
from concurrent.futures import ThreadPoolExecutor

import git
from git.exc import GitCommandError

BASE_URL = "https://git.codelinaro.org/clo/la/"
WORKING_DIR = os.path.realpath("{0}/../../../..".format(os.path.dirname(os.path.realpath(__file__))))
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
    """ Gathers all repos from split system.xml, vendor.xml, and wlan.xml """
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

        wlan_manifest_file = "{0}/.repo/manifests/wlan.xml".format(WORKING_DIR)
        if os.path.exists(wlan_manifest_file):
            with open(wlan_manifest_file) as wlan_manifest:
                wlan_root = Et.parse(wlan_manifest).getroot()
                for child in wlan_root:
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
    ] + list(repo_lst.keys())
    subprocess.run(
        args,
        cwd=WORKING_DIR,
        check=False,
    )


def get_tags_for_project(project_name, repo_path, revision):
    """Finds all WLAN tags pointing at revision for a given CLO project."""
    tags = set()
    local_dir = "{0}/{1}".format(WORKING_DIR, repo_path)
    if os.path.isdir(local_dir):
        try:
            out = subprocess.check_output(
                ["git", "-C", local_dir, "tag", "--points-at", revision],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            tags.update(
                t.strip()
                for t in out.splitlines()
                if t.strip().startswith("WLAN")
            )
        except subprocess.CalledProcessError:
            pass

    if not tags:
        url = "{}{}".format(BASE_URL, project_name)
        try:
            out = subprocess.check_output(
                ["git", "ls-remote", "--tags", url],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    commit, ref = parts[0], parts[1]
                    if commit == revision:
                        tag = ref.replace("refs/tags/", "")
                        if tag.endswith("^{}"):
                            tag = tag[:-3]
                        if tag.startswith("WLAN"):
                            tags.add(tag)
        except subprocess.CalledProcessError:
            pass

    return tags


def find_matched_wlan_tag(wlan_manifest_path):
    """Matches WLAN tags across all repos in wlan manifest."""
    print("Finding matched WLAN tag across all repos in wlan manifest...")
    tree = Et.parse(wlan_manifest_path)
    root = tree.getroot()
    projects = root.findall("project")
    if not projects:
        return None

    def worker(p):
        name = p.get("name")
        path = p.get("path")
        rev = p.get("revision")
        return get_tags_for_project(name, path, rev)

    with ThreadPoolExecutor(max_workers=min(len(projects), 10)) as executor:
        results = list(executor.map(worker, projects))

    valid_results = [r for r in results if r]
    common_tags = set.intersection(*valid_results) if valid_results else set()
    if common_tags:
        matched_tag = sorted(list(common_tags))[-1]
        print(f"Matched WLAN tag: {matched_tag}")
        return matched_tag
    else:
        print("Warning: Could not find a common WLAN tag across all repos in wlan manifest.")
        return None


def merge(repo_lst, is_system, branch, wlan_tag=None):
    """ Merges the necessary repos and lists if a repo succeeds or fails """
    failures = []
    successes = []

    wlan_revisions = {}
    if not is_system:
        wlan_manifest_file = "{0}/.repo/manifests/wlan.xml".format(WORKING_DIR)
        if os.path.exists(wlan_manifest_file):
            with open(wlan_manifest_file) as wlan_manifest:
                wlan_root = Et.parse(wlan_manifest).getroot()
                for child in wlan_root.findall("project"):
                    path = child.get("path")
                    rev = child.get("revision")
                    if path and rev:
                        wlan_revisions[path] = rev

    manifest_name = "system" if is_system else "vendor"
    manifest_file = "{0}/.repo/manifests/{1}.xml".format(WORKING_DIR, manifest_name)
    manifest_revisions = {}
    if os.path.exists(manifest_file):
        with open(manifest_file) as manifest:
            root = Et.parse(manifest).getroot()
            for child in root.findall("project"):
                path = child.get("path")
                rev = child.get("revision")
                if path and rev:
                    manifest_revisions[path] = rev

    for repo in repo_lst:
        if repo == "device/qcom/common":
            print(f"Skipping merge for {repo} as per exception rule.")
            continue  # Skip this repository

        print("Merging " + repo)
        repo_dir = "{0}/{1}".format(WORKING_DIR, repo)
        os.chdir(repo_dir)

        is_wlan = False
        revision = None
        if repo in wlan_revisions:
            revision = wlan_revisions[repo]
            is_wlan = True
        elif repo in manifest_revisions:
            revision = manifest_revisions[repo]

        if not revision:
            print(f"Failed to find revision for {repo}")
            failures.append(repo)
            continue

        # Abort any stale in-progress merge causing exit code 128
        has_merge_head = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if has_merge_head:
            print(f"Aborting previous in-progress merge in {repo}...")
            subprocess.run(["git", "-C", repo_dir, "merge", "--abort"], check=False)

        # Skip if already merged
        if subprocess.run(
            ["git", "-C", repo_dir, "merge-base", "--is-ancestor", revision, "HEAD"],
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            print(f"{repo} is already up to date.")
            successes.append(repo)
            continue

        # Only fetch from CLO if commit is missing locally (avoids HTTP 429 & slowness)
        has_commit = subprocess.run(
            ["git", "-C", repo_dir, "cat-file", "-e", f"{revision}^{{commit}}"],
            stderr=subprocess.DEVNULL,
        ).returncode == 0

        remote_url = "{}{}".format(BASE_URL, repo_lst[repo])
        if not has_commit:
            try:
                print(f"Fetching {revision} from {remote_url}...")
                git.cmd.Git().fetch(remote_url, revision)
            except GitCommandError as git_error:
                print(f"Fetch failed for {repo}: {git_error}")
                failures.append(repo)
                continue

        try:
            # Merge the fetched revision into the current branch with a custom message
            if is_wlan and wlan_tag:
                branch_name = wlan_tag.replace("refs/tags/", "")
            else:
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
    raw_url = f"https://git.codelinaro.org/clo/la/la/{manifest_name}/manifest/-/raw/release/{branch}.xml"
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
            raw_url,
        ],
        check=True,
    )

    wlan_tag = None

    if not is_system:
        # Check for wlan in vendor manifest refs
        tree = Et.parse(manifest_path)
        root = tree.getroot()
        wlan_manifest_tag = None
        wlan_server = "https://git.codelinaro.org/clo/la"
        wlan_project = "techpack/wlan/manifest"

        for refs in root.findall("refs"):
            for image in refs.findall("image"):
                project = image.get("project", "")
                name = image.get("name", "")
                if project == "techpack/wlan/manifest" or project.endswith("/wlan/manifest") or name.startswith("WLAN."):
                    wlan_manifest_tag = image.get("tag")
                    if image.get("server"):
                        wlan_server = image.get("server")
                    if image.get("project"):
                        wlan_project = image.get("project")
                    break
            if wlan_manifest_tag:
                break

        if wlan_manifest_tag:
            print(f"Found WLAN manifest tag from vendor manifest: {wlan_manifest_tag}")
            wlan_manifest_path = "{0}/.repo/manifests/wlan.xml".format(WORKING_DIR)
            wlan_raw_url = f"{wlan_server}/{wlan_project}/-/raw/release/{wlan_manifest_tag}.xml"
            print(f"Downloading WLAN manifest from: {wlan_raw_url}")
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
                    wlan_manifest_path,
                    wlan_raw_url,
                ],
                check=True,
            )

            # Clean up wlan.xml
            with open(wlan_manifest_path) as wlan_xml:
                wlan_tree = Et.parse(wlan_xml)
                wlan_root = wlan_tree.getroot()
                for elem in wlan_root.findall("remote") + wlan_root.findall("default"):
                    wlan_root.remove(elem)
                for refs in wlan_root.findall("refs"):
                    wlan_root.remove(refs)
                wlan_tree.write(wlan_manifest_path)

            print("wlan.xml downloaded successfully.")

            # Find and match WLAN tag across all repos in wlan manifest
            wlan_tag = find_matched_wlan_tag(wlan_manifest_path)
        else:
            print("No WLAN manifest tag found in vendor manifest refs.")

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
    return wlan_tag


def print_results(branch, wlan_tag=None):
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
        msg = branch.replace("refs/tags/", "")
        if wlan_tag:
            msg += f" and {wlan_tag}"
        print(f"{msg} merged successfully!")
    elif not REPOS_RESULTS["Failures"] and not REPOS_RESULTS["Successes"]:
        print("Unable to retrieve any results")


def git_push(remote, refspec, max_retries=3):
    """Pushes to remote using HTTP/1.1 to prevent HTTP2 framing errors, with retries."""
    args = [
        "git",
        "-c", "http.version=HTTP/1.1",
        "push",
        remote,
        refspec,
        "--force",
    ]
    for attempt in range(1, max_retries + 1):
        res = subprocess.run(args, capture_output=True, text=True)
        if res.returncode == 0:
            return True, None
        err = res.stderr.strip()
        if attempt < max_retries:
            time.sleep(2 * attempt)
    return False, err


def push_successful_repos(successful_repos, is_system, branch, wlan_tag=None):
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
        git.cmd.Git().add(f"{manifest_name}.xml")  # Stage changes
        if not is_system and os.path.exists(f"{manifest_path}/wlan.xml"):
            git.cmd.Git().add("wlan.xml")

        # Commit only if there are staged changes
        has_staged_changes = subprocess.run(
            ["git", "-C", manifest_path, "diff", "--cached", "--quiet"],
            stderr=subprocess.DEVNULL,
        ).returncode != 0

        if has_staged_changes:
            if not is_system and wlan_tag:
                commit_msg = f"{manifest_name}: Update to {branch} and {wlan_tag}"
            else:
                commit_msg = f"{manifest_name}: Update to {branch}"
            git.cmd.Git().commit(m=commit_msg, s=True)
    except GitCommandError as git_error:
        print(f"Failed to commit changes in {manifest_path}: {git_error}")

    print(f"Pushing {manifest_path} changes to Neoteric...")
    ok, err = git_push("origin", f"HEAD:{revision}")
    if ok:
        print(f"{manifest_path} pushed successfully.")
    else:
        print(f"Failed to push changes in {manifest_path}: {err}")

    # Push repository changes
    for repo in successful_repos:
        repo_path = f"{WORKING_DIR}/{repo}"
        print(f"Pushing {repo} to Neoteric...")
        os.chdir(repo_path)
        ok, err = git_push("neoteric", f"HEAD:{revision}")
        if ok:
            print(f"{repo} pushed successfully.")
        else:
            print(f"Failed to push {repo}: {err}")


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

    wlan_tag = None

    if len(repo_lst) == 0:
        read_custom_manifest(default_repos)
        if args.dry_run:
            print(list(REPOS_TO_MERGE.keys()))
            quit()
        if REPOS_TO_MERGE:
            wlan_tag = merge_manifest(is_system, args.branch_to_merge)
            default_repos = list_default_repos(is_system)
            REPOS_TO_MERGE.clear()
            read_custom_manifest(default_repos)
            force_sync(REPOS_TO_MERGE)
            merge(REPOS_TO_MERGE, is_system, branch, wlan_tag)
            os.chdir(WORKING_DIR)
            print_results(branch, wlan_tag)
            if args.push:
                if REPOS_RESULTS["Successes"]:  # Push only successful repos
                    push_successful_repos(REPOS_RESULTS["Successes"], is_system, args.branch_to_merge, wlan_tag)
        else:
            print("No repos to sync")
    else:
        if not is_system:
            wlan_manifest_path = "{0}/.repo/manifests/wlan.xml".format(WORKING_DIR)
            if os.path.exists(wlan_manifest_path):
                wlan_tag = find_matched_wlan_tag(wlan_manifest_path)
        force_sync(repo_lst)
        merge(repo_lst, is_system, branch, wlan_tag)
        os.chdir(WORKING_DIR)
        print_results(branch, wlan_tag)
        if args.push:
            if REPOS_RESULTS["Successes"]:  # Push only successful repos
                push_successful_repos(REPOS_RESULTS["Successes"], is_system, args.branch_to_merge, wlan_tag)


if __name__ == "__main__":
    # execute only if run as a script
    main()
