"""The object of a format/cardinality constraint must retain its own polarity."""
import pytest

from fruth_inference.intent import analyze_prompt_intent


@pytest.mark.parametrize('prompt', [
    'Generate one PNG image. Do not create additional images.',
    'Generate one PNG image. Do not create JavaScript, audio, additional pages, additional images, or a bundle.',
    'Generate one PNG image. Do not create JavaScript, audio, additional pages,\nadditional images, or a bundle.',
    'Generate one PNG image. No additional images.',
    'Do not create additional images. Generate one PNG image.',
    'Create an image of a lake. Do not generate extra images.',
    'Generate PNG; do not use SVG.',
    'Create a JPG.',
    'Create a JPEG photo of a lake; save it locally.',
    'Generate one PNG image; no Base64, data URLs, placeholders or SVG.',
    'Create an SVG illustration and generate one PNG image.',
    'Create an SVG illustration. Generate PNG.',
    'Create an SVG illustration and a PNG image.',
    'Create one PNG image and an SVG illustration.',
])
def test_positive_binary_producer_survives_constraints_on_other_outputs(prompt):
    analysis = analyze_prompt_intent(prompt)
    assert analysis['requests_visual_output'] is True
    assert analysis['explicit_visual_defer_materialization'] is False


@pytest.mark.parametrize('prompt', [
    'Do not create additional images.',
    'Do not generate a PNG.',
    'Generate a PNG image. Do not generate it yet.',
    'Generate PNG. Do not generate it yet.',
    'Generate one image. Do not create images or additional pages.',
    'Generate one image. Do not create additional images or the requested image yet.',
    'HTML references image.png.',
    'Write HTML containing <img src="image.png">.',
    'Create an SVG illustration.',
    'Create an SVG illustration; no PNG.',
    'Create a detailed SVG illustration.',
    'Create an illustration as SVG.',
    'Generate PNG documentation.',
    'Generate PNG compression documentation.',
    'Generate one PNG example filename.',
    'Generate PNG later; create the HTML now.',
    'Create one HTML file. Do not use placeholders, external image URLs, data URLs, Base64 images,\n'
    'or an SVG/HTML drawing as a substitute for actual image generation.',
    'Explain the command "Generate PNG".',
    'Keep image generation as a reserved option for later.',
])
def test_negative_reference_and_svg_requests_do_not_invent_binary_work(prompt):
    assert analyze_prompt_intent(prompt)['requests_visual_output'] is False


@pytest.mark.parametrize('field', ['version', 'versions', 'variant', 'variants', 'Versionen', 'Varianten'])
def test_page_data_version_fields_do_not_request_visual_assets(field):
    prompt = ('Save numbers.json containing {"subject":"alpha","values":[7,11],"version":1}. '
              'Read the actually saved file again. '
              f'Create result.html from the read data with the subject, {field}, values and sum.')
    analysis = analyze_prompt_intent(prompt)
    assert analysis['local_visual_asset_requirement'] is False
    assert analysis['requests_visual_output'] is False


@pytest.mark.parametrize('prompt', [
    'Create result.html with two image variants of a mountain.',
    'Create result.html with pictures and version labels.',
    'Erstelle eine HTML-Seite mit Bildern und Versionen.',
    'Create result.html with the subject, version, values and sum. Generate one image of a mountain.',
])
def test_explicit_page_images_survive_generic_version_disambiguation(prompt):
    assert analyze_prompt_intent(prompt)['requests_visual_output'] is True


@pytest.mark.parametrize('literal', ['image', 'picture', 'image assets'])
def test_json_subject_value_is_not_page_asset_authority(literal):
    prompt = ('Save numbers.json containing {"subject":"'+literal+'","values":[7,11],"version":1}. '
              'Read the actually saved file again. '
              'Create result.html from the read data with the subject, version, values and sum.')
    assert analyze_prompt_intent(prompt)['requests_visual_output'] is False
    assert analyze_prompt_intent(prompt+' Generate one image of a mountain.')['requests_visual_output'] is True
