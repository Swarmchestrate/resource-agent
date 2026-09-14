"""Create a local, count-one SAT for resource matching without changing the SAT."""

from copy import deepcopy


def expand_sat_counts(sat):
    """Return (matching SAT, instance-to-original ID mapping).

    Host counts are expanded deterministically. Colocation groups must have
    equal counts and are copied as corresponding pairs/groups of instances.
    This document is for matching; application manifests use the original SAT.
    """
    expanded = deepcopy(sat)
    template = expanded.get('service_template', {})
    nodes = template.get('node_templates', {})
    instance_ids = {}
    used_names = set(nodes)

    for name, node in nodes.items():
        if node.get('type') != 'swch:Microservice':
            continue
        hosts = [req['host'] for req in node.get('requirements', [])
                 if 'host' in req]
        if len(hosts) > 1:
            raise ValueError(f'{name}: multiple host requirements are not supported')
        host = hosts[0] if hosts else {}
        count = host.get('count', 1) if isinstance(host, dict) else 1
        if type(count) is not int or count < 1:
            raise ValueError(f'{name}: host count must be a positive integer')
        names = [name] if count == 1 else [f'{name}-{i}' for i in range(1, count + 1)]
        for instance in names:
            if instance != name:
                if instance in used_names:
                    raise ValueError(f'{name}: expanded name {instance!r} already exists')
                if len(instance) > 63:
                    raise ValueError(f'{name}: expanded name {instance!r} exceeds 63 characters')
                used_names.add(instance)
        instance_ids[name] = names

    expanded_nodes = {}
    origins = {}
    for name, node in nodes.items():
        for instance in instance_ids.get(name, [name]):
            clone = deepcopy(node)
            if name in instance_ids:
                origins[instance] = name
                for requirement in clone.get('requirements', []):
                    if isinstance(requirement.get('host'), dict):
                        requirement['host']['count'] = 1
            expanded_nodes[instance] = clone
    if 'node_templates' in template:
        template['node_templates'] = expanded_nodes

    policies = []
    policy_names = {name for policy in template.get('policies', []) for name in policy}
    for policy in template.get('policies', []):
        for name, details in policy.items():
            targets = details.get('targets', [])
            if details.get('type') == 'swch:Scheduling.Colocation' and targets:
                if any(target not in instance_ids for target in targets):
                    raise ValueError(f'{name}: colocation targets must name microservices')
                counts = {len(instance_ids[target]) for target in targets}
                if len(counts) != 1:
                    raise ValueError(f'{name}: colocated microservices must have equal host counts')
                count = counts.pop()
                for index in range(count):
                    policy_name = name if count == 1 else f'{name}-{index + 1}'
                    if count > 1:
                        if policy_name in policy_names:
                            raise ValueError(f'{name}: expanded policy {policy_name!r} already exists')
                        policy_names.add(policy_name)
                    clone = deepcopy(details)
                    clone['targets'] = [instance_ids[target][index] for target in targets]
                    policies.append({policy_name: clone})
            else:
                clone = deepcopy(details)
                if 'targets' in clone:
                    clone['targets'] = [instance for target in targets
                                        for instance in instance_ids.get(target, [target])]
                policies.append({name: clone})
    if 'policies' in template:
        template['policies'] = policies
    return expanded, origins
