"""Parameter names shared by the PDK and device-family views of a circuit graph."""
from dataclasses import replace


def remap_parameters(graph, renames):
    """Return parameter values and groups in the view's columns, leaving the source graph intact.

    Preserve insertion order and the existing collision rule: a second value for a
    mapped column keeps its original key. Unmapped values and unchanged groups are
    borrowed, as in both original views.
    """
    parameters = {}
    for device_id, values in graph.parameters.items():
        columns = renames.get(device_id)
        if not columns:
            parameters[device_id] = values
            continue
        moved = {}
        for key, value in values.items():
            target = columns.get(key, key)
            moved[target if target not in moved else key] = value
        parameters[device_id] = moved
    groups = []
    for group in graph.parameter_groups:
        members = tuple(replace(member, parameter=renames[member.device_id].get(member.parameter, member.parameter))
                        if member.device_id in renames else member for member in group.members)
        groups.append(replace(group, members=members) if members != group.members else group)
    return parameters, groups
