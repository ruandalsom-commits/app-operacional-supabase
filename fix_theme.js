const fs = require('fs');
let content = fs.readFileSync('index.html', 'utf8');

content = content.replace(/--azul-escuro: #0F1849/g, '--azul-escuro: #061A0C');
content = content.replace(/--azul-principal: #2C67EA/g, '--azul-principal: #009C3B');
content = content.replace(/--azul-intermediario: #1B3FAC/g, '--azul-intermediario: #002776');
content = content.replace(/--menta-viva: #2CEABC/g, '--menta-viva: #FFDF00');
content = content.replace(/--menta-suave: #B4FFED/g, '--menta-suave: #FFF17A');
content = content.replace(/--azul-gelo: #B4E4FF/g, '--azul-gelo: #D1E8D9');

content = content.replace(/44,234,188/g, '255,223,0');
content = content.replace(/44,103,234/g, '0,156,59');
content = content.replace(/8,14,46/g, '3,16,6');
content = content.replace(/13,20,65/g, '10,36,18');
content = content.replace(/10,16,50/g, '5,24,10');
content = content.replace(/15,24,73/g, '8,40,16');
content = content.replace(/#080e2e/g, '#031006');
content = content.replace(/rgba\(180,228,255/g, 'rgba(209,232,217');

fs.writeFileSync('index.html', content, 'utf8');
console.log('Feito com sucesso e sem quebrar acentos!');
