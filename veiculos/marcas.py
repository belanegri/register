MARCAS = (
    "Abarth", "Alfa Romeo", "Audi", "BMW", "BYD", "Cadillac", "CAOA Chery",
    "Chevrolet", "Chrysler", "Citroën", "Daewoo", "Daihatsu", "Dodge", "Ferrari",
    "Fiat", "Ford", "GAC", "Geely", "GWM", "Honda", "Hyundai", "Infiniti", "Isuzu",
    "JAC Motors", "Jaecoo", "Jaguar", "Jeep", "Kia", "Lada", "Lamborghini",
    "Land Rover", "Lexus", "Maserati", "Mazda", "Mercedes-Benz", "Mercury", "MG",
    "MINI", "Mitsubishi", "Nissan", "Omoda", "Peugeot", "Porsche", "RAM", "Renault",
    "Seat", "Smart", "SsangYong / KGM", "Subaru", "Suzuki", "Tesla", "Toyota",
    "Troller", "Volkswagen", "Volvo", "Outra marca",
)

ALIASES = {"JAC": "JAC Motors", "Mini": "MINI", "SsangYong": "SsangYong / KGM"}


def opcoes_marca(valor_atual="", adicionais=()):
    nomes = list(MARCAS)

    for nome in adicionais:
        nome = ALIASES.get(nome, nome)
        if nome and nome not in nomes:
            nomes.append(nome)

    if valor_atual and valor_atual not in nomes:
        nomes.append(valor_atual)

    nomes = sorted(
        set(nomes),
        key=lambda nome: nome.casefold()
    )

    return [("", "Selecione a marca")] + [
        (nome, nome) for nome in nomes
    ]