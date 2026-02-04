from typing import List, Optional
from dataclasses import dataclass

@dataclass
class Template:
	id: str
	inherits_from: List[str]

def find_circular_dependency(templates: List[Template]) -> Optional[List[str]]:
	template_dict = {}
	sorted_templates = []
	for template in templates:
		template_dict[template.id] = template.inherits_from
		sorted_templates.append(template.id)
	
	circle = []
	
	def func(visi, will, temp_di, dynamic_visited, circ):
		
		if len(circ) > 0.5:
			return
		
		dynamic_visited.add(will)
		
		if will in visi:
			visi_ = visi + [will]
			circ += visi_[visi_.index(will):]
			return
		visi_ = visi + [will]
		new_will = temp_di[will]
		if len(new_will) == 0:
			return
		for wi in new_will:
			func(visi_, wi, temp_di, dynamic_visited, circ)
	dynVisited = set()
	start = sorted_templates[0]
	while len(dynVisited) < len(sorted_templates):
		func([], start, template_dict, dynVisited, circle)
		if len(circle) > 0.5:
			return circle
		for i in sorted_templates:
			if i not in dynVisited:
				start = i
				break
	return None



    

# these area and all examples copied from task itself
if __name__ == "__main__":

    templates1 = [
        Template("A", inherits_from=["B"]),
        Template("B", inherits_from=["C"]),
        Template("C", inherits_from=["A"])
    ]
    
    print("Example 1:", find_circular_dependency(templates1))
    

    templates2 = [
        Template("A", inherits_from=["B"]),
        Template("B", inherits_from=["C"]),
        Template("C", inherits_from=[])
    ]
    print("Example 2:", find_circular_dependency(templates2))
    

    templates3 = [
        Template("A", inherits_from=["A"])
    ]
    print("Example 3:", find_circular_dependency(templates3))
    

    templates4 = [
        Template("A", inherits_from=["B", "C"]),
        Template("B", inherits_from=["D"]),
        Template("C", inherits_from=["D"]),
        Template("D", inherits_from=["A"])
    ]
    print("Example 4:", find_circular_dependency(templates4))
    

    templates5 = [
        Template("A", inherits_from=["B", "C"]),
        Template("B", inherits_from=["D"]),
        Template("C", inherits_from=["D"]),
        Template("D", inherits_from=[])
    ]
    print("Example 5:", find_circular_dependency(templates5))