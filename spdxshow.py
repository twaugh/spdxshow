#!/usr/bin/python

# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see
# <https://www.gnu.org/licenses/>.

import argparse
from collections import Counter
from functools import cache
import json
import sys

from packageurl import PackageURL


def argparser():
    parser = argparse.ArgumentParser(description="Show SPDX elements")
    subparsers = parser.add_subparsers(dest="command")
    packages = subparsers.add_parser("packages", aliases=["p"])
    packages.add_argument("file", help="SPDX file", type=open)
    relationships = subparsers.add_parser(
        "relationships",
        aliases=["r"],
        description="Show relationships between packages in Graph::Easy format. Pipe to eg `graph-easy --as=boxart`.",
    )
    relationships.add_argument("file", help="SPDX file", type=open)
    relationships.add_argument("--no-hints", help="Disable placement hinting", action="store_true")
    return parser


def truncate(l):
    l = sorted(list(l))
    if len(l) > 10:
        l[10:] = [f"... ({len(l) - 10} more)"]

    return l


def display_package(pkg):
    purls = [
        ref["referenceLocator"]
        for ref in pkg.get("externalRefs", [])
        if ref["referenceType"] == "purl"
    ]
    if purls:
        by_noq = {}
        for purl in purls:
            noq = purl.rsplit("?", maxsplit=1)[0]
            by_noq.setdefault(noq, []).append(purl)

        noq = Counter(by_noq).most_common()[0][0]
        purl = PackageURL.from_string(by_noq[noq][0])

        if "download_url" in purl.qualifiers:
            return purl.qualifiers["download_url"]
        version = purl.version
        if version.startswith("sha256:"):
            version = version[: 7 + 5] + "..."

        arch = purl.qualifiers.get("arch", "")
        if arch:
            arch = f".{arch}"
        elif purl.type == "oci":
            arch = ".index"

        return f"{purl.type}{arch}: {purl.name} {version}"

    ver = pkg.get("versionInfo")
    if ver and ver != "NOASSERTION":
        return f"{pkg['name']} {ver}"

    return pkg["name"]


def show_relationships(args):
    doc = json.load(args.file)

    relationships = doc.get("relationships", [])
    packages = {pkg["SPDXID"]: pkg for pkg in doc.get("packages", [])}

    # Make it easy to look up inbound and outbound relationship connections
    # for a package
    relationships = [
        r
        for r in relationships
        if r["spdxElementId"] in packages and r["relatedSpdxElement"] in packages
    ]
    fwdrelmap = {}
    for rel in relationships:
        rellist = fwdrelmap.setdefault(rel["spdxElementId"], {}).setdefault(
            rel["relationshipType"], []
        )
        rellist.append(rel["relatedSpdxElement"])

    revrelmap = {}
    for rel in relationships:
        rellist = revrelmap.setdefault(rel["relatedSpdxElement"], {}).setdefault(
            rel["relationshipType"], []
        )
        rellist.append(rel["spdxElementId"])

    # Group packages by the inbound and outbound connections they have
    # with other packages
    connections = {}
    for package in packages:
        ins = []
        for rel, pkgfrom in revrelmap.get(package, {}).items():
            ins.append((tuple(pkgfrom), rel))
        outs = []
        for rel, pkgto in fwdrelmap.get(package, {}).items():
            outs.append((tuple(pkgto), rel))

        connections.setdefault((tuple(ins), tuple(outs)), []).append(package)

    for equivalent in filter(lambda pkgs: len(pkgs) > 1, connections.values()):
        # Remove duplicate relationships
        primary = equivalent[0]
        others = equivalent[1:]
        relationships = [
            rel
            for rel in relationships
            if (
                rel["spdxElementId"] not in others
                and rel["relatedSpdxElement"] not in others
            )
        ]

        # Combine equivalent relationships
        all_equiv = "\\n".join(truncate(equivalent))
        for rel in relationships:
            if rel["spdxElementId"] == primary:
                rel["spdxElementId"] = all_equiv
            if rel["relatedSpdxElement"] == primary:
                rel["relatedSpdxElement"] = all_equiv

    packages = {pkg["SPDXID"]: display_package(pkg) for pkg in packages.values()}
    edges = []
    first = None
    offset = 2
    hints = not args.no_hints
    for rel in relationships:
        purls = [packages.get(line, line) for line in rel["spdxElementId"].split("\\n")]
        lhs = "\\n".join(purls)
        purls = [
            packages.get(line, line) for line in rel["relatedSpdxElement"].split("\\n")
        ]
        rhs = "\\n".join(purls)
        rel_type = rel["relationshipType"]
        edge = f"[ {lhs} ] -- {rel_type} --> [ {rhs} ]"

        if first is None:
            first = lhs

        if rhs != first and hints:
            edge += f" {{ origin: {first}; offset: 0,{offset}; }}"
            offset += 2

        edges.append(edge)

    if hints:
        print("graph { flow: south; }")

    print("\n".join(edges))


def show_packages(args):
    doc = json.load(args.file)
    packages = doc.get("packages", [])
    print("\n".join([display_package(pkg) for pkg in packages]))


def main():
    parser = argparser()
    args = parser.parse_args()
    if args.command in ("relationships", "r"):
        show_relationships(args)
    elif args.command in ("packages", "p"):
        show_packages(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
