#!/usr/bin/env python 2.7
# by Kevin Bonham, PhD (2015)
# for Dutton Lab, Harvard Center for Systems Biology, Cambridge MA
# CC-BY

import pymongo
import os
from itertools import groupby, combinations, combinations_with_replacement
from bson.objectid import ObjectId
import pandas as pd
import KvDataStructures as kv
from DataImport import import_16S
from skbio import DNA
from skbio.alignment import StripedSmithWaterman
from matplotlib import pyplot as plt
import numpy as np

def output_hits_csv():
    hits = kv.get_collection('hits')
    if not os.path.isdir('hits/'):
       os.makedirs('hits/')

    df_index = [
        'parent_locus',
        'parent_annotation',
        'parent_seq',
        'parent_contig',
        'parent_start',
        'parent_end',
        'parent_strand',
        'hit_species',
        'hit_tag',
        'hit_annotation',
        'hit_seq',
        'hit_contig',
        'hit_start',
        'hit_end',
        'hit_strand',
    ]
    
    for record in hits.find():
        query_species = record['species']
        df = pd.DataFrame()

        for query_id in record['hits']:
            list_of_hits = record['hits'][query_id]
            if list_of_hits:
                query_species_collection = kv.get_collection(query_species)
                query_record = query_species_collection.find_one({'_id':ObjectId(query_id)})
                
                for hit in list_of_hits:

                    hit_species = hit[0]
                    hit_id = hit[1]
                    hit_species_collection = kv.get_collection(hit_species)
                    hit_record = hit_species_collection.find_one({'_id':ObjectId(hit_id)})
                    hit_record['kvtag']
                    query_annotation = query_record['annotation'].replace(',','')
                    hit_annotation = hit_record['annotation'].replace(',','')
                    
                    series = pd.Series(
                        [query_record['kvtag'],
                        query_annotation,
                        query_record['dna_seq'],
                        query_record['location']['contig'],
                        query_record['location']['start'],
                        query_record['location']['end'],
                        query_record['location']['strand'],
                        hit_record['species'],
                        hit_record['kvtag'],
                        hit_annotation,
                        hit_record['dna_seq'],
                        hit_record['location']['contig'],
                        hit_record['location']['start'],
                        hit_record['location']['end'],
                        hit_record['location']['strand'],
                        ],
                        index=df_index,
                        name=hit_record['species']
                    )

                    df=df.append(series)
        df.to_csv('hits/{}_hits.csv'.format(query_species), cols=df_index)
            

def output_one_fasta(mongo_record, out_file='output.fna'):
    with open(out_file, 'w+') as output_handle:
        output_handle.write(
            '>{0}|{1}\n{2}\n'.format(
                mongo_record['species'],
                str(mongo_record['_id']),
                mongo_record['dna_seq'],
                )
            )

def get_groups():
    # dutton_list = ['JB182', 'JB7', 'JB5', 'JB4', 'JB37', 'JB110', 'JB170', 'JB193', 'JB196', 'JB197', 'Brevibacterium undefined']
    # wolfe_list = ["962_8", "738_8", "862_7", "947_11", "862_8", "341_9", "738_10",]
    all_hits = kv.get_collection('hits')
    groups_list = []
    for h in all_hits.find():
        current_species = h['species']

        # if any([x in current_species for x in dutton_list] or [y in current_species for y in wolfe_list]):
        current_species_islands = get_islands(h['species'])
        
        # each sublist represents one island...
        for island in current_species_islands:
            hit_set = set() # container for hits 
            for gene_id in island:
                gene_hits = h['hits'][gene_id[1]]
                
                # Pulls each hit id tuple, then appends it to group_set
                for hit in gene_hits:
                    hit_set.add((hit[0], hit[1]))
            # add id tuples for hits to island list...
            island.update(hit_set)
            # And add new island (with multiple species) to groups_list
            groups_list.append(list(island))

    # Since each species' islands are built independently, there's a lot of redundancy
    # So... Collapse lists that contain shared elements and deduplicate
    return map(list, collapse_lists(groups_list))

def output_groups(output_file='default', min_group_size=2):
    if output_file == 'default':
        output_file = 'groups.csv'.format(kv.db.name)
        df_index = [
            'groups',
            'species',
            'kvtag',
            'contig',
            'start',
            'end',
            'strand',
            'annotation',
            'dna_seq',
        ]
        df = pd.DataFrame()
        group_no= 0
        groups_list = get_groups()
        groups_list.sort(key=len, reverse=True)

        for group in groups_list:
            if len(group) >= min_group_size:
                group_no += 1
                # Entry is `(species, id)`
                for entry in group:
                    db_handle = kv.get_mongo_record(*entry)
                    
                    annotation = db_handle['annotation'].replace(',','')
                    series = pd.Series(
                        [str(group_no).zfill(3),
                        db_handle['species'],
                        db_handle['kvtag'],
                        db_handle['location']['contig'],
                        db_handle['location']['start'],
                        db_handle['location']['end'],
                        db_handle['location']['strand'],
                        annotation,
                        db_handle['dna_seq']
                        ],
                        index=df_index,
                        name=db_handle['kvtag']
                    )
                    df=df.append(series)
        df.to_csv(output_file, cols=df_index)

def output_groups_by_species(min_group_size=2):
    all_species = kv.get_species_collections()
    groups_list = get_groups()
    groups_list.sort(key=len, reverse=True)

    groups_df = pd.DataFrame(data={n:0 for n in all_species}, index=[str(x+1) for x in range(0, len(groups_list))])

    group_no = 0
    for group in groups_list:
        if len(group) >= min_group_size:
            group_no += 1
            species_in_group = [x[0] for x in group]
            for species in species_in_group:
                groups_df[species][group_no-1] = 1
    groups_df.to_csv('groups_by_species.csv')

def output_compare_matrix():
    groups = get_groups()
    all_species = kv.get_species_collections() 
    cds_df = pd.DataFrame(data={n:0 for n in all_species}, index=all_species)
    nt_df = pd.DataFrame(data={n:0 for n in all_species}, index=all_species)
    groups_df = pd.DataFrame(data={n:0 for n in all_species}, index=all_species)

    for pair in combinations(all_species, 2):
        print "====\nComparing {} and {}".format(pair[0], pair[1])
        shared_cds, shared_nt = pair_compare(pair[0],pair[1])
        shared_groups = 0
        if kv.get_genus(pair[0]) == kv.get_genus(pair[1]):
            print "Oops! They're the same genus... moving on\n===="
            continue
        elif shared_cds == 0:
            print "Oops! Looks like they don't share anything... moving on\n===="
            continue
        else:
            for group in get_groups():           
                if [x for x in group if x[0] == pair[0] and any(y[0] == pair[1] for y in group)]:
                    shared_groups +=1

            cds_df[pair[0]][pair[1]] = shared_cds
            nt_df[pair[0]][pair[1]] = shared_nt
            groups_df[pair[0]][pair[1]] = shared_groups
            print "shared cds: {}\nshared nt: {}\nshared groups: {}\n====".format(shared_cds, shared_nt, shared_groups)

    cds_df.to_csv('cds_matrix.csv'.format(kv.db.name))
    nt_df.to_csv('nt_matrix.csv'.format(kv.db.name))
    groups_df.to_csv('groups_matrix.csv' .format(kv.db.name))

def pair_compare(species_1, species_2):    
    shared_CDS = 0
    shared_nt = 0

    s1_genes = kv.get_collection('hits').find_one({'species':species_1})
    
    for gene in s1_genes['hits']:
        if s1_genes['hits'][gene]:
            for hit in s1_genes['hits'][gene]:
                if hit[0] == species_2:
                    shared_CDS += 1
                    species_2_record = kv.get_mongo_record(hit[0],hit[1])
                    hit_loc = species_2_record['location']
                    shared_nt += hit_loc['end'] - hit_loc['start']
    return shared_CDS, shared_nt

def get_islands(species_name):
    islands = []
    species_hits_list = []
    
    # Add mongo_record for each hit in any gene
    all_hits = kv.get_collection('hits')
    species_hits = all_hits.find_one({'species':species_name})['hits']

    
    for query_id in species_hits:
        if species_hits[query_id]:
            species_hits_list.append(
                kv.get_mongo_record(species_name, query_id)
                )

    for entry_1 in species_hits_list:
        entry_recorded = False
        for entry_2 in species_hits_list:
            if entry_1 == entry_2:
                pass
            elif entry_1['location']['contig'] != entry_2['location']['contig']:
                pass
            else:
                location_1 = entry_1['location']
                location_2 = entry_2['location']
                if abs(location_1['end'] - location_2['start']) <= 5000:
                    entry_recorded = True
                    islands.append([
                        (entry_1['species'], str(entry_1['_id'])),
                        (entry_2['species'], str(entry_2['_id']))
                    ])
        if not entry_recorded:
            islands.append([(entry_1['species'], str(entry_1['_id']))])

    return collapse_lists(islands)

def get_gene_distance(seq_1, seq_2):
    query = StripedSmithWaterman(seq_1)
    alignment = query(seq_2)
    return (2.0 - float(alignment.optimal_alignment_score) / float(len(alignment.query_sequence)))    

def get_16S_distance(species_1, species_2):
    if not '16S' in kv.get_collections():
        import_16S()
    
    # print 'Aligning:', species_1, species_2
    s1_ssu = str(kv.db['16S'].find_one({'species':species_1})['dna_seq'])
    s2_ssu = str(kv.db['16S'].find_one({'species':species_2})['dna_seq'])
    return get_gene_distance(s1_ssu, s2_ssu)

def output_all_16S():
    if not '16S' in kv.get_collections():
        import_16S()

    print "Making fasta of all 16S in database {}".format(kv.db.name)
    with open('{}_16S.fna'.format(kv.db.name), 'w+') as output_handle:
        for record in kv.get_collection('16S').find():
            output_handle.write(
                '>{0}\n{1}\n'.format(
                    record['species'],
                    record['dna_seq'],
                    )
                )

def output_distance_matrix():
    all_species = kv.get_species_collections() 
    distance_matrix = pd.DataFrame(data={n:0.0 for n in all_species}, index=all_species)
    
    for pair in combinations_with_replacement(all_species, 2):
        distance = get_16S_distance(pair[0], pair[1])
        print distance
        distance_matrix[pair[0]][pair[1]] = distance

    distance_matrix.to_csv('distance_matrix.csv')

"""Basic Use Functions"""
def collapse_lists(list_of_lists):
    # example input: [[1,2,3],[3,4],[5,6,7],[1,8,9,10],[11],[11,12],[13],[5,12]]
    # example output: [[1,2,3,4,8,9,10],[5,6,7,11,12],[13]]
    # from stackoverflow user YXD: http://stackoverflow.com/questions/30917226/collapse-list-of-lists-to-eliminate-redundancy
    result = []
    for l in list_of_lists:
        s = set(l)

        matched = [s]
        unmatched = []
        # first divide into matching and non-matching groups
        for g in result:
            if s & g:
                matched.append(g)
            else:
                unmatched.append(g)
        # then merge matching groups
        result = unmatched + [set().union(*matched)]
    return result

def get_tag_int(kvtag):
    return int(kvtag[-5:])


if __name__ == '__main__':
    import sys
    kv.mongo_init('more_genomes')
    os.chdir('/Users/KBLaptop/computation/kvasir/data/output/more_genomes/')
    output_groups_by_species(4)