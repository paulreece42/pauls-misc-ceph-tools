# pauls-misc-ceph-tools
Miscellaneous Ceph tooling I've written over the years, basically a buncha gists

- **cephfs-quota-prometheus** - prometheus exporter to crawl / walk a CephFS filesystem (danger: slow), find directories with CephFS quotas set on them, and export fullness. With the end result being a monitoring alert, hopefully before quota is hit