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
    relationships.add_argument(
        "--no-hints", help="Disable placement hinting", action="store_true"
    )
    return parser


def truncate(l):
    l = sorted(list(l))
    if len(l) > 10:
        l[10:] = [f"... ({len(l) - 10} more)"]

    return l


def display_package(pkg, detail=0):
    purls = [
        ref["referenceLocator"]
        for ref in pkg.get("externalRefs", [])
        if ref["referenceType"] == "purl"
    ]
    pfn = pkg.get("packageFileName")
    ver = pkg.get("versionInfo")
    descr = None
    match detail:
        case 0 | 1:
            if purls:
                by_noq = {}
                for purl in purls:
                    noq = purl.rsplit("?", maxsplit=1)[0]
                    by_noq.setdefault(noq, []).append(purl)

                noq = Counter(by_noq).most_common()[0][0]
                purl = PackageURL.from_string(by_noq[noq][0])

                if "download_url" in purl.qualifiers:
                    descr = purl.qualifiers["download_url"]
                else:
                    version = purl.version
                    if version.startswith("sha256:"):
                        version = version[: 7 + 5] + "..."

                    arch = purl.qualifiers.get("arch", "")
                    if arch:
                        arch = f".{arch}"
                    elif purl.type == "oci":
                        arch = ".index"

                    descr = f"{purl.type}{arch}: {purl.name} {version}"
            elif pfn and pfn != "NOASSERTION":
                descr = pfn
            elif ver and ver != "NOASSERTION":
                descr = f"{pkg['name']} {ver}"
            else:
                descr = pkg["name"]

            # Add detail in case of duplicates
            if detail == 1:
                if purls or (pfn and pfn != "NOASSERTION"):
                    descr = f"{pkg['name']}: {descr}"
                else:
                    descr = pkg["SPDXID"]
        case 2:
            descr = pkg["SPDXID"]

    return descr


def show_relationships(args):
    doc = json.load(args.file)

    relationships = doc.get("relationships", [])
    packages = {pkg["SPDXID"]: pkg for pkg in doc.get("packages", [])}
    packagedescrs = get_package_descriptions(doc)

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


    edges = []
    first = None
    offset = 2
    hints = not args.no_hints
    seen = set()
    for rel in relationships:
        purls = [packagedescrs.get(line, line) for line in rel["spdxElementId"].split("\\n")]
        lhs = "\\n".join(purls)
        purls = [
            packagedescrs.get(line, line) for line in rel["relatedSpdxElement"].split("\\n")
        ]
        rhs = "\\n".join(purls)
        rel_type = rel["relationshipType"]

        if first is None:
            first = lhs
            seen.add(first)

        lhint = rhint = ""
        if hints and lhs not in seen:
            lhint = f" {{ origin: {first}; offset: 0,{offset}; }}"
            seen.add(lhs)
            offset += 2

        if hints and rhs not in seen:
            rhint = f" {{ origin: {first}; offset: 0,{offset}; }}"
            seen.add(rhs)
            offset += 2

        edge = f"[ {lhs} ]{lhint} -- {rel_type} --> [ {rhs} ]{rhint}"

        edges.append(edge)

    if hints:
        print("graph { flow: south; }")

    print("\n".join(edges))


def get_package_descriptions(doc):
    packages = {pkg["SPDXID"]: pkg for pkg in doc.get("packages", [])}
    packagedescrs = {pkg["SPDXID"]: display_package(pkg) for pkg in packages.values()}

    # Add more detail in case of duplicate package descriptions
    detail = 0
    while True:
        packagedescr_values = list(packagedescrs.values())
        pkg_dups = {spdxid for spdxid, descr in packagedescrs.items() if packagedescr_values.count(descr) > 1}
        if not pkg_dups:
            break

        detail += 1
        if detail > 2:
            # Give up
            break

        for spdxid in pkg_dups:
            packagedescrs[spdxid] = display_package(packages[spdxid], detail=detail)

    return packagedescrs


def show_packages(args):
    doc = json.load(args.file)
    packagedescrs = get_package_descriptions(doc)
    print("\n".join(packagedescrs.values()))


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
