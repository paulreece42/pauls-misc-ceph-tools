#!/bin/env python3
#
# Quick and dirty script to scan X dirs deep on CephFS for file
# or bytes quotas, and dump the output for inclusion into Prometheus
# node_exporter
#
# This info seems difficult to get at, operationally. I need to dig into
# the source of Ceph a bit more someday, and see if there's an easier way,
# maybe directly looking at certain omap values for example, rather than walking
# the entire filesystem...
#
# Has not been tested extensively
#
# usage, crontab, five min:
# */5 * * * * myuser flock -xn /var/lock/quota_cron.lock /opt/cephfs_quota_exporter.py
#

import os
import os.path
import cephfs as libcephfs

cephfs = None   # holds CephFS Python bindings
DEPTH = 2 # depth to recurse
PATH = '/' # path to start
SHOW_JUST_QUOTA = True # only output dirs that have a quota. False means prints all dirs walked
PROMFILE = '/var/lib/prometheus/node-exporter/cephfs_quota.prom'

def setup_cephfs():
    """
    Mounting a cephfs
    """
    global cephfs
    try:
        cephfs = libcephfs.LibCephFS(conffile='')
        cephfs.mount()
    except libcephfs.ObjectNotFound as e:
        print('couldn\'t find ceph configuration not found')
        sys.exit(e.get_error_code())
    except libcephfs.Error as e:
        print(e)
        sys.exit(e.get_error_code())

def lsdir(mydir):
    try:
        dir_handle = cephfs.opendir(mydir)
        while True:
            entry = cephfs.readdir(dir_handle)
            if entry is None:
                break  # End of directory
            print(entry.d_name) # entry.d_name is the name of the file or subdirectory
        cephfs.closedir(dir_handle)
    except libcephfs.Error as e:
        print(f"CephFS Error: {e}")

def walk_cephfs(start_path, max_depth, current_depth=0):
    mydirs=[]
    if current_depth > max_depth:
        return
    try:
        dir_handle = cephfs.opendir(start_path)
    except cephfs.Error as e:
        print(f"Error opening directory {start_path}: {e}")
        return
    while True:
        entry = cephfs.readdir(dir_handle)
        if not entry:
            break
        entry_name = entry.d_name.decode('utf-8')
        if entry_name in ['.', '..']:
            continue  # Skip current and parent directory entries
        full_path = os.path.join(start_path, entry_name)
        try:
            # Check if it's a directory
            stat_info = cephfs.lstat(full_path)
            if stat_info.st_mode & 0o40000:  # Check for S_IFDIR
                #print(f"Directory at depth {current_depth}: {full_path}")
                mydirs.append(full_path)
                # Recurse into subdirectories
                subdirs = walk_cephfs(full_path, max_depth, current_depth + 1)
                # append subdirs to list
                if subdirs:
                    for dir in subdirs:
                        mydirs.append(dir)
        except cephfs.Error as e:
            print(f"Error stating entry {full_path}: {e}")
            continue
    return(mydirs)
    # Close the directory
    cephfs.closedir(dir_handle)


if __name__ == '__main__':
    setup_cephfs()
    dirs = walk_cephfs(PATH, DEPTH)
    cephfs_custom_bytes_size = []
    cephfs_custom_bytes_quota = []
    cephfs_custom_files_quota = []
    cephfs_custom_files_count = []
    for mydir in dirs:
        mydirstats = cephfs.stat(mydir)
        try:
            mybytesquota = cephfs.getxattr(mydir, 'ceph.quota.max_bytes').decode('utf-8')
        except libcephfs.NoData:
            mybytesquota = None
        try:
            myfilesquota = cephfs.getxattr(mydir, 'ceph.quota.max_files').decode('utf-8')
        except libcephfs.NoData:
            myfilesquota = None
        try:
            myfilescount = cephfs.getxattr(mydir, 'ceph.dir.rentries').decode('utf-8')
        except libcephfs.NoData:
            myfilescount = None
        # mydirstats.st_size
        if not SHOW_JUST_QUOTA or mybytesquota or myfilesquota:
            cephfs_custom_bytes_size.append("""cephfs_custom_bytes_size{path="%s"} %s\n""" % (mydir,mydirstats.st_size))
            if mybytesquota:
                cephfs_custom_bytes_quota.append("""cephfs_custom_bytes_quota{path="%s"} %s\n""" % (mydir,mybytesquota))
            if myfilesquota:
                cephfs_custom_files_quota.append("""cephfs_custom_files_quota{path="%s"} %s\n""" % (mydir,myfilesquota))
            if myfilescount:
                cephfs_custom_files_count.append("""cephfs_custom_files_count{path="%s"} %s\n""" % (mydir,myfilescount))
    with open(PROMFILE, "w") as f:
        if len(cephfs_custom_bytes_size) > 0:
            f.write("# HELP cephfs_custom_bytes_size size of filesystem in bytes\n")
            f.write("# TYPE cephfs_custom_bytes_size gauge\n")
            for entry in cephfs_custom_bytes_size:
               f.write(entry)
        if len(cephfs_custom_bytes_quota) > 0:
            f.write("# HELP cephfs_custom_bytes_quota quota limit of filesystem in bytes\n")
            f.write("# TYPE cephfs_custom_bytes_quota gauge\n")
            for entry in cephfs_custom_bytes_quota:
               f.write(entry)
        if len(cephfs_custom_files_quota) > 0:
            f.write("# HELP cephfs_custom_files_quota quota limit of number of files\n")
            f.write("# TYPE cephfs_custom_files_quota gauge\n")
            for entry in cephfs_custom_files_quota:
               f.write(entry)
        if len(cephfs_custom_files_count) > 0:
            f.write("# HELP cephfs_custom_files_count number of files in filesystem\n")
            f.write("# TYPE cephfs_custom_files_count gauge\n")
            for entry in cephfs_custom_files_count:
               f.write(entry)
        f.write("\n") # end in newline, per Prom docs
