#/bin/bash

#6 months of Bwctl data 15552000
####10g Throughput results
./ps_generate_data.py -k esmond -d base_rate -t 15552000 --key-prefix "throughput" -m "EC7E5AF67F8746C8AEF41E60288F3F59" --minval 0 --maxval 10000000000 -w 14400

#6 months of Owamp data
####1 minute (base) summaries of one-way delay
./ps_generate_data.py -k esmond -d histogram -t 15552000 --keep-data --key-prefix "histogram_owdelay" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 0 --maxval 1000 --sample-size 600 -w 60

#####1 day summaries of one-way delay
./ps_generate_data.py -k esmond -d histogram -t 15552000 --keep-data --key-prefix "histogram_owdelay" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 0 --maxval 1000 --sample-size 864000 -T aggregation -w 86400

####1 minute (base) summaries of ttl
./ps_generate_data.py -k esmond -d histogram -t 15552000 --keep-data --key-prefix "histogram_ttl" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 9 --maxval 10 --sample-size 600 -w 60

####1 minute (base) summaries of number of packets lost
./ps_generate_data.py -k esmond -d base_rate -t 15552000 --keep-data --key-prefix "packet_count_lost" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 0 --maxval 600 -w 60

####1 minute (base) summaries of number of packets sent
./ps_generate_data.py -k esmond -d base_rate -t 15552000 --keep-data --key-prefix "packet_count_sent" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 0 --maxval 600 -w 60

####1 minute (base) summaries of number of packet duplicates
./ps_generate_data.py -k esmond -d base_rate -t 15552000 --keep-data --key-prefix "packet_duplicates" -m "0CB19291FB6D40EAA1955376772BF5D2" --minval 0 --maxval 600 -w 60
