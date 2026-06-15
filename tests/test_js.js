/**
 * Test automatique JS NEXORA
 * Lance avec : node tests/test_js.js
 * Valide que tous les fichiers JS sont syntaxiquement corrects
 */
const fs = require('fs');
const path = require('path');

const jsFiles = [
    'static/js/nexora-core.js',
    'static/js/modules/stock.js',
    'static/js/modules/logistique.js',
    'static/js/modules/commercial.js',
    'static/js/modules/comptabilite.js',
    'static/js/modules/caisse.js',
    'static/js/modules/rh.js',
    'static/js/modules/consolidation.js',
    'static/js/modules/multisite.js',
    'static/js/modules/rapports.js',
    'static/js/modules/parametres.js',
];

const root = path.join(__dirname, '..');

let allOk = true;
jsFiles.forEach(function(file) {
    const fullPath = path.join(root, file);
    if (!fs.existsSync(fullPath)) {
        allOk = false;
        console.log('MANQUANT: ' + file);
        return;
    }
    const code = fs.readFileSync(fullPath, 'utf8');
    // Verifier qu'il n'y a pas de backticks problematiques
    const backtickLines = code.split('\n').filter(function(line) {
        return line.includes('`') && !line.trim().startsWith('//');
    });
    if (backtickLines.length > 0) {
        console.log('BACKTICKS dans ' + file + ':');
        backtickLines.slice(0, 3).forEach(function(l) {
            console.log('   ' + l.substring(0, 80));
        });
    }
    try {
        new Function(code);
        console.log('OK ' + file);
    } catch (e) {
        allOk = false;
        console.log('ERREUR ' + file + ': ' + e.message);
    }
});

console.log(allOk ? '\nTOUS LES FICHIERS JS SONT VALIDES' :
                    '\nDES ERREURS EXISTENT - CORRIGER AVANT LIVRAISON');
process.exit(allOk ? 0 : 1);
